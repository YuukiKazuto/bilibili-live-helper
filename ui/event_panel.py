"""互动消息实时显示面板（rules/07「互动消息实时显示」）。

- format_event / category_label 为纯函数，便于测试与阶段 2 复用。
- EventPanel 只展示不参与：不做过滤、不进播报队列，所有事件都显示，
  与播报开关完全解耦。默认嵌在主窗口，也可重挂载到置顶悬浮窗。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from platforms.base import LiveEvent

# 事件类型 → 类别标签
_LABELS = {
    "danmaku": "弹幕",
    "gift": "礼物",
    "super_chat": "醒目留言",
    "entry": "进场",
    "follow": "关注",
    "guard": "上舰",
    "like": "点赞",
}


def category_label(event_type: str) -> str:
    """事件类型 → 中文类别标签（未知类型归为「其他」）。"""
    return _LABELS.get(event_type, "其他")


def format_event(event: LiveEvent) -> tuple[str, str]:
    """统一事件 → (类别标签, 展示文本)。纯函数，不含 Qt 依赖。"""
    label = category_label(event.type)
    name = event.user_name
    if event.type == "danmaku":
        text = f"{name} 说：{event.content}"
    elif event.type == "gift":
        if event.is_blind:
            text = f"{name} 投喂了盲盒爆出的{event.gift_name}（¥{event.amount:g}）"
        else:
            text = f"{name} 投喂了 {event.num} 个{event.gift_name}（¥{event.amount:g}）"
    elif event.type == "super_chat":
        text = f"{name} 发来醒目留言（¥{event.amount:g}）：{event.content}"
    elif event.type == "guard":
        text = f"{name} 开通了{event.guard_title or '舰长'}"
    else:
        # entry / follow / like / 未知类型
        text = f"{name} {event.content}".strip() or name
    return label, text


class EventPanel(QListWidget):
    """互动消息滚动列表（主窗口与悬浮窗共用同一实例，切换不丢历史）。"""

    MAX_ROWS = 300  # 防止长时间直播内存无限增长

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.setEditTriggers(QListWidget.EditTrigger.NoEditTriggers)

    def add_event(self, event: LiveEvent) -> None:
        """追加一条事件（槽函数，UI 主线程执行）。"""
        label, text = format_event(event)
        item = QListWidgetItem(f"[{label}] {text}")
        item.setData(Qt.ItemDataRole.UserRole, event.type)
        self.addItem(item)
        while self.count() > self.MAX_ROWS:
            self.takeItem(0)
        self.scrollToBottom()
