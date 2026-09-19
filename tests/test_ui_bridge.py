"""UI 桥接层测试：服务线程事件 → Qt 信号跨线程投递（rules/07「跨线程投递」）。"""
import threading

from platforms.base import LiveEvent
from ui.bridge import ServiceBridge


def test_post_event_emits_signal_from_worker_thread(qtbot):
    """服务线程调用 post_event 时，event_received 信号在 UI 事件循环中触发。"""
    bridge = ServiceBridge()
    event = LiveEvent(type="danmaku", user_name="测试用户", content="你好")

    with qtbot.waitSignal(bridge.event_received, timeout=2000) as blocker:
        # 模拟服务线程投递（rules/07：回调在服务线程触发，须经信号转投递）
        t = threading.Thread(target=bridge.post_event, args=(event,))
        t.start()
        t.join()

    assert blocker.args == [event]


def test_post_event_delivers_multiple_events_in_order(qtbot):
    """多条事件按投递顺序送达。"""
    bridge = ServiceBridge()
    events = [
        LiveEvent(type="danmaku", user_name="A", content="1"),
        LiveEvent(type="gift", user_name="B", gift_name="小花花", amount=1.0),
    ]
    received: list[LiveEvent] = []
    bridge.event_received.connect(received.append)

    with qtbot.waitSignal(bridge.event_received, timeout=2000):
        for e in events:
            t = threading.Thread(target=bridge.post_event, args=(e,))
            t.start()
            t.join()

    qtbot.waitUntil(lambda: len(received) == len(events), timeout=2000)
    assert received == events
