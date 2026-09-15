"""全局播报队列：顺序播报 + 付费事件插队 + 绝不打断当前条目。

规则（.claude/rules/02-features.md「播报队列规则」）：
1. 所有播报进入统一队列，一条读完才读下一条。
2. 原文与感谢成对：一个播报单元（list[str]）内的文本连续播完，不被插队。
3. 付费事件（礼物/舰长/醒目留言）优先于普通事件入队。
4. 优先级只影响等待顺序，正在播报的条目必须读完。
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

# 优先级：数值越小越先播
PRIORITY_PAID = 0    # 礼物投喂 / 大航海上舰 / 醒目留言（用户花了钱）
PRIORITY_NORMAL = 1  # 弹幕 / 进场 / 关注 / 点赞

# 付费事件类型 → 高优先级
_PAID_TYPES = {"gift", "guard", "super_chat"}


def priority_of(event_type: str) -> int:
    return PRIORITY_PAID if event_type in _PAID_TYPES else PRIORITY_NORMAL


class BroadcastQueue:
    """播报单元队列 + 单工作协程顺序消费。

    同优先级内 FIFO；付费单元排到所有普通单元之前；
    正在播的单元（含其中每条文本）必须完整读完。
    """

    def __init__(self, speak) -> None:
        """speak: async def speak(text: str) -> None，播完返回。"""
        self._speak = speak
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._seq = 0  # 同优先级 FIFO 序号
        self._worker: asyncio.Task | None = None

    def start(self) -> None:
        """启动消费协程（幂等）。"""
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    def enqueue(self, unit: list[str], priority: int = PRIORITY_NORMAL) -> None:
        """入队一个播报单元（原文+感谢成对，连续播完）。非阻塞。"""
        if not unit:
            return
        self._seq += 1
        self._queue.put_nowait((priority, self._seq, unit))

    async def _run(self) -> None:
        while True:
            priority, _seq, unit = await self._queue.get()
            try:
                for text in unit:
                    logger.debug("播报(优先级=%d): %s", priority, text)
                    # await 保证「一条读完才读下一条」；插队只发生在 get() 之间
                    await self._speak(text)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — 播报失败不拖垮队列
                logger.exception("播报单元失败: %r", unit)
            finally:
                self._queue.task_done()
