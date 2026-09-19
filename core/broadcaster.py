"""播报策略：开关过滤 + 模板播报文案 + 感谢文案，组装为成对播报单元。

规则来源 .claude/rules/02-features.md（修改文案/开关/队列行为必须同步该文档）：
- 第一层开关：模板播报（如弹幕 → [昵称]说：[内容]）
- 第二层开关：附加感谢播报（与第一层解耦）
- 原文+感谢成对入队；付费事件高优先级；顺序由 BroadcastQueue 保证
"""
import logging

from config.preferences import Preferences
from core.broadcast_queue import BroadcastQueue, priority_of

logger = logging.getLogger(__name__)


class Broadcaster:
    """根据用户偏好把统一事件转换为播报单元并投递到全局队列。"""

    def __init__(self, prefs: Preferences, queue: BroadcastQueue) -> None:
        self.prefs = prefs
        self.queue = queue

    # ── 对外入口（供事件总线回调）──

    async def on_event(self, event) -> None:  # event: platforms.base.LiveEvent
        unit = self.build_texts(event)
        if unit:
            # 付费事件（礼物/舰长/醒目留言）插队；正在播的不受影响
            self.queue.enqueue(unit, priority=priority_of(event.type))

    # ── 纯逻辑：事件 → 播报单元（模板播报在前，感谢紧随其后，成对出现）──

    def build_texts(self, event) -> list[str]:
        texts: list[str] = []

        # 第一层：模板播报
        raw = self._raw_text(event)
        if raw is not None:
            texts.append(raw)

        # 第二层：感谢播报（紧随模板播报，同一单元内不被插队）
        thanks = self._thanks_text(event)
        if thanks:
            texts.append(thanks)

        return texts

    # ── 模板播报文案（.claude/rules/02-features.md「事件模板播报文案」）──

    def _raw_enabled(self, etype: str) -> bool:
        mapping = {
            "danmaku": self.prefs.broadcast_danmaku,
            "gift": self.prefs.broadcast_gift,
            "super_chat": self.prefs.broadcast_super_chat,
            "entry": self.prefs.broadcast_entry,
            "follow": self.prefs.broadcast_follow,
            "guard": self.prefs.broadcast_guard,
            "like": self.prefs.broadcast_like,
        }
        return mapping.get(etype, False)

    def _raw_text(self, event) -> str | None:
        if not self._raw_enabled(event.type):
            return None
        name = event.user_name
        match event.type:
            case "danmaku":
                return f'{name}说：“{event.content}”'
            case "gift":
                if event.is_blind:
                    return f"{name}投喂了盲盒爆出的{event.gift_name}"
                return f"{name}投喂了 {event.num} 个{event.gift_name}"
            case "super_chat":
                return f'{name}发来醒目留言：{event.content}'
            case "entry":
                return f"{name}进入直播间"
            case "follow":
                return f"{name}关注了直播间"
            case "guard":
                return f"{name}开通了{event.guard_title}"
            case "like":
                return f"{name}点了赞"
        return None

    # ── 感谢播报文案（金额阈值默认 50 元，≥ 阈值追加「老板大气」）──

    def _thanks_text(self, event) -> str | None:
        p = self.prefs
        name = event.user_name
        threshold = p.amount_threshold

        if event.type == "gift" and p.thanks_gift:
            if event.is_blind:
                text = f"感谢{name}投喂的盲盒爆出的{event.gift_name}"
            else:
                text = f"感谢{name}投喂的 {event.num} 个{event.gift_name}"
            if event.amount >= threshold:
                text += "，老板大气"
            return text

        if event.type == "super_chat" and p.thanks_super_chat:
            text = f"感谢{name}的醒目留言"
            if event.amount >= threshold:
                text += "，老板大气"
            return text

        if event.type == "follow" and p.thanks_follow:
            return f"感谢{name}的关注"

        if event.type == "guard" and p.thanks_guard:
            return f"感谢{name}的舰长，老板大气"

        # 舰长进场播报（独立开关；进场事件且用户为舰长）
        if event.type == "entry" and p.guard_entry_welcome and event.is_guard:
            return f"欢迎{name}进入直播间"

        return None
