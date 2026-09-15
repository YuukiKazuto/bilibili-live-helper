"""事件总线：弹幕源 → 播报策略 的解耦中枢。

平台适配层（platforms/）将平台事件归一化为 LiveEvent 后发布到总线；
订阅方（播报策略、日志、UI 面板等）不感知任何平台细节。
"""
import asyncio
import logging
from collections import defaultdict
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

# 统一事件模型：所有平台弹幕源必须归一化为此结构后才能进入总线
try:  # 延迟导入避免循环依赖
    from platforms.base import LiveEvent  # noqa: F401
except ImportError:  # pragma: no cover
    LiveEvent = None  # type: ignore


class EventBus:
    """进程内异步事件总线（阶段 2 移植时可替换为消息队列等实现）。"""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[object], Awaitable[None] | None]]] = defaultdict(list)

    def subscribe(
        self,
        handler: Callable[[object], Awaitable[None] | None],
        event_type: str | None = None,
    ) -> None:
        """订阅事件；event_type 为 None 表示订阅全部事件。"""
        self._subscribers[event_type or "*"].append(handler)

    async def publish(self, event: object) -> None:
        """发布事件，分发给对应订阅者与全量订阅者。"""
        etype = getattr(event, "type", None)
        for handler in self._subscribers.get(etype, []) + self._subscribers["*"]:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001 — 单个订阅者异常不影响其他
                logger.exception("事件处理异常: %r", event)
