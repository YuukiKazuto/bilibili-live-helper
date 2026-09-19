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
    # LIVE_OPEN_PLATFORM_SEND_GIFT：礼物投喂（字段以官方文档为准）
    uname = d.get("uname", "")
    gift_name = d.get("gift_name", "")
    # price/r_price 单位是金瓜子（1000 = 1元 = 10电池）；盲盒场景为爆出道具价值
    # r_price 是实际价值，存在时优先
    price = d.get("r_price") or d.get("price", 0) or 0
    # 官方文档：数量字段为 gift_num（非 amount）
    num = d.get("gift_num", 1) or 1
    blind = d.get("blind_gift") or {}
    is_blind = bool(blind.get("status"))
    return [LiveEvent(
        type="gift",
        user_name=uname,
        amount=price * num / 1000,  # 金瓜子 → 元
        num=num,
        gift_name=gift_name,
        is_blind=is_blind,
        extra={"gift_id": d.get("gift_id"), "blind_gift_id": blind.get("blind_gift_id")},
    )]


def _super_chat(d: dict) -> list[LiveEvent]:
    # LIVE_OPEN_PLATFORM_SUPER_CHAT：醒目留言（官方文档：金额字段为 rmb，单位元）
    uname = d.get("uname", "")
    msg = d.get("message", "")
    return [LiveEvent(
        type="super_chat",
        user_name=uname,
        content=msg,
        amount=float(d.get("rmb", 0) or 0),
        extra={"message_id": d.get("message_id")},
    )]


def _entry(d: dict) -> list[LiveEvent]:
    # LIVE_OPEN_PLATFORM_LIVE_ROOM_ENTER：进场消息（官方文档无航海信息字段）
    uname = d.get("uname", "")
    return [LiveEvent(type="entry", user_name=uname)]


def _follow(d: dict) -> list[LiveEvent]:
    # LIVE_OPEN_PLATFORM_FOLLOW：关注
    return [LiveEvent(
        type="follow",
        user_name=d.get("uname", ""),
    )]


def _guard(d: dict) -> list[LiveEvent]:
    # LIVE_OPEN_PLATFORM_GUARD：大航海（舰长/提督/总督）
    # 官方文档：昵称在 user_info.uname；price 为金瓜子；数量字段 guard_num
    user_info = d.get("user_info") or {}
    uname = user_info.get("uname", "")
    level = d.get("guard_level", 3)  # 3=舰长 2=提督 1=总督
    title = {1: "总督", 2: "提督", 3: "舰长"}.get(level, "舰长")
    return [LiveEvent(
        type="guard",
        user_name=uname,
        amount=(d.get("price", 0) or 0) * (d.get("guard_num", 1) or 1) / 1000,
        num=d.get("guard_num", 1) or 1,
        guard_title=title,
        extra={"guard_level": level, "guard_unit": d.get("guard_unit", "")},
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
    "LIVE_OPEN_PLATFORM_LIVE_ROOM_ENTER": _entry,  # 官方 CMD（原 LIVE_ENTER_ROOM 为臆造）
    "LIVE_OPEN_PLATFORM_FOLLOW": _follow,
    "LIVE_OPEN_PLATFORM_GUARD": _guard,            # 官方 CMD（原 GUARD_BUY 为臆造）
    "LIVE_OPEN_PLATFORM_LIKE": _like,
}
