"""B站开放平台事件 → 统一事件模型（LiveEvent）的归一化层。

命令名与字段以官方长连数据协议文档为准
（.claude/rules/05-bilibili-api.md 文档链接 2）。
"""
import logging

from platforms.base import LiveEvent

logger = logging.getLogger(__name__)


def parse_command(data: dict) -> list[LiveEvent]:
    """把一条长连命令归一化为 LiveEvent 列表（一条命令可能对应多个事件）。"""
    cmd = data.get("cmd", "")
    d = data.get("data", {})
    handler = _HANDLERS.get(cmd)
    if handler is None:
        logger.debug("未处理的命令: %s", cmd)
        return []
    return handler(d)


def _danmaku(d: dict) -> list[LiveEvent]:
    # LIVE_OPEN_PLATFORM_DM：弹幕
    uname = d.get("uname", "")
    msg = d.get("msg", "")
    return [LiveEvent(
        type="danmaku",
        user_name=uname,
        content=msg,
        extra={"msg_id": d.get("msg_id"), "fans_medal": d.get("fans_medal_level")},
    )]


def _gift(d: dict) -> list[LiveEvent]:
    # LIVE_OPEN_PLATFORM_SEND_GIFT：礼物投喂
    uname = d.get("uname", "")
    gift_name = d.get("gift_name", "")
    # price 为单价（元），amount 为数量；总金额 = 单价 × 数量
    price = d.get("price", 0) or 0
    num = d.get("amount", 1) or 1
    return [LiveEvent(
        type="gift",
        user_name=uname,
        amount=price * num,
        gift_name=gift_name,
        extra={"gift_id": d.get("gift_id"), "num": num},
    )]


def _super_chat(d: dict) -> list[LiveEvent]:
    # LIVE_OPEN_PLATFORM_SUPER_CHAT：醒目留言
    uname = d.get("uname", "")
    msg = d.get("message", "")
    return [LiveEvent(
        type="super_chat",
        user_name=uname,
        content=msg,
        amount=d.get("price", 0) or 0,
        extra={"message_id": d.get("message_id")},
    )]


def _entry(d: dict) -> list[LiveEvent]:
    # LIVE_OPEN_PLATFORM_LIVE_ENTER_ROOM：进场消息
    uname = d.get("uname", "")
    is_guard = d.get("guard_info", {}).get("guard_level", 0) > 0
    return [LiveEvent(
        type="entry",
        user_name=uname,
        is_guard=is_guard,
    )]


def _follow(d: dict) -> list[LiveEvent]:
    # LIVE_OPEN_PLATFORM_FOLLOW：关注
    return [LiveEvent(
        type="follow",
        user_name=d.get("uname", ""),
    )]


def _guard(d: dict) -> list[LiveEvent]:
    # LIVE_OPEN_PLATFORM_GUARD_BUY：大航海（舰长/提督/总督）
    uname = d.get("uname", "")
    level = d.get("guard_level", 3)  # 3=舰长 2=提督 1=总督
    title = {1: "总督", 2: "提督", 3: "舰长"}.get(level, "舰长")
    return [LiveEvent(
        type="guard",
        user_name=uname,
        amount=d.get("price", 0) or 0,
        guard_title=title,
        extra={"guard_level": level, "num": d.get("num", 1)},
    )]


def _like(d: dict) -> list[LiveEvent]:
    # LIVE_OPEN_PLATFORM_LIKE：点赞
    return [LiveEvent(
        type="like",
        user_name=d.get("uname", ""),
    )]


_HANDLERS = {
    "LIVE_OPEN_PLATFORM_DM": _danmaku,
    "LIVE_OPEN_PLATFORM_SEND_GIFT": _gift,
    "LIVE_OPEN_PLATFORM_SUPER_CHAT": _super_chat,
    "LIVE_OPEN_PLATFORM_LIVE_ENTER_ROOM": _entry,
    "LIVE_OPEN_PLATFORM_FOLLOW": _follow,
    "LIVE_OPEN_PLATFORM_GUARD_BUY": _guard,
    "LIVE_OPEN_PLATFORM_LIKE": _like,
}
