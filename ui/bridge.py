"""服务层 ↔ Qt 信号桥接（rules/07「跨线程投递」）。

服务线程中触发的事件回调不得直接操作控件：桥接层只负责把服务线程的调用
转成 Qt 信号，槽函数由 Qt 自动在 UI 主线程执行。

阶段 2 迁移说明：本层是 UI 与 service 接口之间唯一的胶水，远程实现下
只需把 post_event 换成网络推送入口，UI 其余代码零改动。
"""
from PySide6.QtCore import QObject, Signal


class ServiceBridge(QObject):
    """把服务线程回调转成 Qt 信号（线程安全：emit 可从任意线程调用）。"""

    # 收到统一事件（platforms.base.LiveEvent），参数为事件对象
    event_received = Signal(object)

    def post_event(self, event) -> None:
        """服务线程调用：投递一条统一事件到 UI 线程。"""
        self.event_received.emit(event)
