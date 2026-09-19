"""桌面 UI 主窗口（阶段 1，PySide6）。

- 默认单窗口：顶部工具栏（开始/停止、状态、悬浮、设置）+ 互动消息面板。
- 悬浮模式：消息面板重挂载到独立置顶窗口，切换不丢历史。
- 登录：身份码为空时由 run_app() 先弹登录对话框，登录后不再出现身份码入口。
- UI 只依赖 service 接口，不 import core/platforms/tts（rules/07「UI 复用约束」）。

跨线程约定（rules/07）：service.subscribe_events 的回调在服务线程触发，
这里只做 bridge.post_event（Qt 信号 emit），渲染槽在 UI 主线程执行。
"""
import asyncio
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config.preferences import Preferences
from service.base import ServiceError
from ui.bridge import ServiceBridge
from ui.event_panel import EventPanel
from ui.login_dialog import LoginDialog, need_login
from ui.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)


class FloatingWindow(QWidget):
    """置顶悬浮窗：承载互动消息面板，可拖动。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            None,
            Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setWindowTitle("互动消息（悬浮）")
        self.resize(420, 600)
        self._layout = QVBoxLayout(self)


class MainWindow(QMainWindow):
    """主窗口：服务控制 + 互动消息实时显示。"""

    def __init__(self, service, bridge: ServiceBridge | None = None) -> None:
        super().__init__()
        self.service = service
        self.prefs: Preferences = service.get_preferences()
        self.bridge = bridge or ServiceBridge()
        self._floating: FloatingWindow | None = None
        self._stopping = False  # 停止进行中（后台线程），同步计时器据此恢复按钮

        self.setWindowTitle("B站直播弹幕播报辅助")
        self.resize(560, 720)

        # 顶部工具栏
        self.start_button = QPushButton("开始连接")
        self.status_label = QLabel("未连接")
        self.floating_button = QPushButton("悬浮📌")
        self.floating_button.setCheckable(True)
        self.settings_button = QPushButton("⚙ 设置")

        bar = QHBoxLayout()
        bar.addWidget(self.start_button)
        bar.addWidget(self.status_label)
        bar.addStretch(1)
        bar.addWidget(self.floating_button)
        bar.addWidget(self.settings_button)

        # 互动消息面板（rules/07：只展示不参与，与播报开关解耦）
        self.panel = EventPanel()

        # 警告条（密钥缺失等，无警告时隐藏）
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #d33;")
        self.warning_label.hide()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(bar)
        layout.addWidget(self.panel)
        layout.addWidget(self.warning_label)
        self.setCentralWidget(central)

        # 信号连接
        self.start_button.clicked.connect(self._toggle_service)
        self.floating_button.clicked.connect(self._toggle_floating)
        self.settings_button.clicked.connect(self._open_settings)
        self.bridge.event_received.connect(self.panel.add_event)

        # 服务线程回调 → Qt 信号（跨线程投递，rules/07）
        service.subscribe_events(self.bridge.post_event)

        # 周期同步运行状态（覆盖平台断线等 UI 外部状态变化）
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(1000)
        self._sync_timer.timeout.connect(self._sync_state)
        self._sync_timer.start()
        self._sync_state()

    # ── 服务控制 ──

    def _toggle_service(self) -> None:
        if self.service.is_running():
            # 停止可能耗时（close 握手等待），放后台线程执行，UI 不冻结
            self._stopping = True
            self.start_button.setEnabled(False)
            self.start_button.setText("停止中…")
            self.status_label.setText("正在停止…")

            def worker() -> None:
                self.service.stop()
                self._stopping = False  # GIL 下布尔赋值，同步计时器据此恢复按钮

            import threading
            threading.Thread(target=worker, name="service-stop", daemon=True).start()
            return
        try:
            self.service.start()
        except ServiceError as exc:
            # 行内提示，不用模态弹窗打断
            self.status_label.setText(f"启动失败：{exc}")
            return
        self._sync_state()

    def _sync_state(self) -> None:
        running = self.service.is_running()
        if running:
            self.status_label.setText("状态：运行中")
            self.start_button.setText("停止连接")
            self.start_button.setEnabled(True)
        else:
            self.start_button.setText("开始连接")
            if not self._stopping:  # 停止完成后恢复按钮
                self.start_button.setEnabled(True)
            if self.status_label.text().startswith("状态：运行中"):
                self.status_label.setText("状态：已断开")
            elif not self.status_label.text().startswith(("正在停止", "启动失败", "状态：")):
                self.status_label.setText("未连接")
        self._refresh_warnings()

    def _refresh_warnings(self) -> None:
        warnings = self.service.warnings()
        if warnings:
            self.warning_label.setText("\n".join(warnings))
            self.warning_label.show()
        else:
            self.warning_label.hide()

    # ── 悬浮切换 ──

    def _toggle_floating(self) -> None:
        if self._floating is None:
            floating = FloatingWindow(self)
            floating.layout().addWidget(self.panel)
            floating.show()
            self.resize(560, 80)
            self._floating = floating
            self.floating_button.setText("取消悬浮")
        else:
            self.centralWidget().layout().insertWidget(1, self.panel)
            self.resize(560, 720)
            self._floating.close()
            self._floating.deleteLater()
            self._floating = None
            self.floating_button.setText("悬浮📌")

    # ── 设置 ──

    def _open_settings(self) -> None:
        from service.base import ModelInfo

        models: list[ModelInfo] = []
        try:
            models = self.service.list_models()
        except Exception:  # noqa: BLE001 — 模型列表失败不阻塞设置窗
            logger.exception("[UI] 获取模型列表失败")
        dialog = SettingsDialog(
            self.prefs,
            save_fn=self.service.save_preferences,
            models=models,
            downloader=self._download_model,
        )
        dialog.exec()
        self._sync_state()

    def _download_model(self, model_id: str, progress) -> None:
        """在对话框的工作线程中执行：跑独立事件循环执行异步下载。"""
        asyncio.run(self.service.download_model(model_id, progress))

    # ── 关闭 ──

    def closeEvent(self, event) -> None:
        if self._floating is not None:
            self._floating.close()
        self.service.stop()
        super().closeEvent(event)


def run_app(service) -> int:
    """UI 程序入口：按需弹登录 → 主窗口事件循环。"""
    app = QApplication.instance() or QApplication([])
    prefs = service.get_preferences()
    if need_login(prefs):
        login = LoginDialog(prefs, save_fn=service.save_preferences)
        if login.exec() != LoginDialog.DialogCode.Accepted:
            return 0  # 未登录直接退出
    window = MainWindow(service)
    window.show()
    return app.exec()
