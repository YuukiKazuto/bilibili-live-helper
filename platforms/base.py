"""平台弹幕源抽象基类与统一事件模型。

所有平台（B站及未来其他平台）的事件必须归一化为 LiveEvent，
经 on_event 回调送入事件总线。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Awaitable


@dataclass
class LiveEvent:
    """统一事件模型（平台无关）。

    type 取值: danmaku | gift | super_chat | entry | follow | guard | like
    与播报开关的映射见 .claude/rules/02-features.md。
    """

    type: str            # 事件类型（上述枚举值）
    user_name: str       # 用户昵称
    content: str = ""    # 文本内容（弹幕内容 / 醒目留言内容）
    amount: float = 0.0  # 金额（元）：礼物/醒目留言用
    num: int = 1         # 数量：礼物件数等
    gift_name: str = ""  # 礼物名称
    guard_title: str = ""  # 大航海档位（舰长/提督/总督）
    is_guard: bool = False  # 用户是否舰长（舰长进场播报用）
    extra: dict | None = None  # 平台附加字段（扩展预留）


# 事件发布回调：平台收到原始消息 → 归一化 → 回调
EventCallback = Callable[[LiveEvent], Awaitable[None]]


class PlatformBase(ABC):
    """弹幕源抽象基类。"""

    def __init__(self, on_event: EventCallback) -> None:
        self.on_event = on_event

    @abstractmethod
    async def connect(self) -> None:
        """建立连接（含鉴权）。"""

    @abstractmethod
    async def run(self) -> None:
        """进入事件循环（收消息/心跳），阻塞直至断开。"""

    @abstractmethod
    async def close(self) -> None:
        """优雅关闭（断开连接、结束应用会话等）。"""
