"""主窗口组装测试：启动/停止、事件流转、悬浮切换、警告展示。"""
import pytest

from platforms.base import LiveEvent
from service.base import ServiceError
from ui.app import MainWindow
from ui.bridge import ServiceBridge


class FakeService:
    """最小服务替身：满足 MainWindow 依赖，可注入失败。"""

    def __init__(self, fail_start=False):
        self.prefs = type("P", (), {"bili_id_code": "CODE"})()
        self.fail_start = fail_start
        self.started = 0
        self.stopped = 0
        self._running = False
        self._callbacks = []
        self.warnings_list = ["云端 TTS 密钥未配置"]

    def get_preferences(self):
        return self.prefs

    def save_preferences(self):
        pass

    def start(self):
        if self.fail_start:
            raise ServiceError("请先填写主播身份码")
        self.started += 1
        self._running = True

    def stop(self, timeout=10.0):
        self.stopped += 1
        self._running = False

    def is_running(self):
        return self._running

    def subscribe_events(self, cb):
        self._callbacks.append(cb)

    def unsubscribe_events(self, cb):
        pass

    def warnings(self):
        return self.warnings_list


def make_window(qtbot, **kwargs):
    service = FakeService(**kwargs)
    window = MainWindow(service, bridge=ServiceBridge())
    qtbot.addWidget(window)
    window.show()
    return service, window


@pytest.fixture()
def window(qtbot):
    return make_window(qtbot)


def test_start_button_drives_service(qtbot, window):
    service, w = window
    w.start_button.click()
    assert service.started == 1
    qtbot.waitUntil(lambda: "运行中" in w.status_label.text(), timeout=2000)
    assert w.start_button.text() == "停止连接"

    w.start_button.click()
    assert service.stopped == 1


def test_start_failure_shows_inline_error(qtbot):
    service, w = make_window(qtbot, fail_start=True)
    w.start_button.click()
    assert "身份码" in w.status_label.text()
    assert w.start_button.text() == "开始连接"


def test_events_flow_to_panel(qtbot, window):
    service, w = window
    # 模拟服务线程投递事件
    w.bridge.post_event(LiveEvent(type="danmaku", user_name="小明", content="你好"))
    qtbot.waitUntil(lambda: w.panel.count() == 1, timeout=2000)
    assert "小明" in w.panel.item(0).text()
    assert "弹幕" in w.panel.item(0).text()


def test_floating_toggle_reparents_panel(qtbot, window):
    service, w = window
    from PySide6.QtCore import Qt

    # 默认嵌在主窗口
    assert w.panel.window() is w

    w.floating_button.click()
    assert w.panel.window() is not w  # 独立窗口
    assert bool(w.panel.window().windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    assert w.floating_button.text().startswith("取消悬浮")

    w.floating_button.click()
    assert w.panel.window() is w  # 回到主窗口，历史不丢


def test_floating_toggle_keeps_history(qtbot, window):
    service, w = window
    w.bridge.post_event(LiveEvent(type="like", user_name="阿甲"))
    qtbot.waitUntil(lambda: w.panel.count() == 1, timeout=2000)

    w.floating_button.click()
    assert w.panel.count() == 1  # 重挂载不丢消息
    w.floating_button.click()
    assert w.panel.count() == 1


def test_warnings_shown_in_warning_label(qtbot, window):
    service, w = window
    assert "云端 TTS 密钥未配置" in w.warning_label.text()


def test_stop_does_not_block_ui_and_shows_stopping(qtbot):
    """停止在后台线程执行：UI 不冻结，按钮显示停止中并自动恢复。"""
    import time as _time

    class SlowStopService(FakeService):
        def stop(self, timeout=10.0):
            _time.sleep(0.4)  # 模拟 close 握手等待
            self._running = False

    service = SlowStopService()
    window = MainWindow(service, bridge=ServiceBridge())
    qtbot.addWidget(window)
    window.show()

    window.start_button.click()
    qtbot.waitUntil(lambda: service.is_running(), timeout=2000)

    window.start_button.click()  # 触发停止
    assert not window.start_button.isEnabled()  # 停止期间禁用，UI 未被阻塞
    assert "停止" in window.start_button.text()

    qtbot.waitUntil(lambda: window.start_button.isEnabled(), timeout=3000)
    assert window.start_button.text() == "开始连接"
