"""设置对话框：两层播报开关、金额阈值、TTS 模式与本地模型（rules/02、04）。

UI 只读写 Preferences 对象并经 save_fn 持久化，不直接依赖核心模块
（rules/07「UI 复用约束」）。模型列表与下载能力由调用方注入：
- models: service.list_models() 结果
- downloader: 同步阻塞的下载函数 (model_id, progress_cb)，对话框在工作
  线程中执行，进度经 Qt 信号投递回 UI 线程（rules/07「跨线程投递」）。
"""
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config.preferences import Preferences

# rules/02 开关字段 → 中文标签（顺序即展示顺序；字段名即 Preferences 字段）
_LAYER1_FIELDS = [
    ("broadcast_danmaku", "弹幕"),
    ("broadcast_gift", "礼物投喂"),
    ("broadcast_super_chat", "醒目留言"),
    ("broadcast_entry", "进场消息"),
    ("broadcast_follow", "关注通知"),
    ("broadcast_guard", "大航海上舰"),
    ("broadcast_like", "点赞"),
]
_LAYER2_FIELDS = [
    ("thanks_gift", "礼物投喂感谢"),
    ("thanks_super_chat", "醒目留言感谢"),
    ("thanks_follow", "关注通知感谢"),
    ("thanks_guard", "大航海上舰感谢"),
    ("thanks_like", "点赞感谢"),
]
_GUARD_ENTRY_FIELD = [("guard_entry_welcome", "舰长进场播报")]

SWITCH_FIELDS: list[tuple[str, str]] = _LAYER1_FIELDS + _LAYER2_FIELDS + _GUARD_ENTRY_FIELD


class SettingsDialog(QDialog):
    """模态设置窗：确定即写回 Preferences 并调 save_fn。"""

    # 下载进度（已完成字节, 总字节或 None）；下载结束(成功, 提示文本)
    download_progress = Signal(int, object)
    download_finished = Signal(bool, str)

    def __init__(self, prefs: Preferences, save_fn=None, models=None,
                 speakers=None, downloader=None, parent=None) -> None:
        super().__init__(parent)
        self.prefs = prefs
        self._save_fn = save_fn
        self._downloader = downloader
        self._downloading = False
        self._downloaded: set[str] = {m.model_id for m in (models or []) if m.downloaded}
        self._speakers = list(speakers or [])
        self.setWindowTitle("设置")
        self.setModal(True)

        self.switches: dict[str, QCheckBox] = {}
        layout = QVBoxLayout(self)

        layout.addWidget(self._build_switch_group("播报开关（勾选即播报事件原文）", _LAYER1_FIELDS))
        layout.addWidget(self._build_switch_group("附加感谢播报（独立可选）", _LAYER2_FIELDS))
        layout.addWidget(self._build_switch_group("其他", _GUARD_ENTRY_FIELD))
        layout.addWidget(self._build_tts_group(models or []))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── 构建分区 ──

    def _build_switch_group(self, title: str, fields: list[tuple[str, str]]) -> QWidget:
        box = QGroupBox(title)
        flow = QHBoxLayout()
        for name, label in fields:
            cb = QCheckBox(label)
            cb.setChecked(getattr(self.prefs, name))
            self.switches[name] = cb
            flow.addWidget(cb)
        # 换行收缩（窗口变窄时可换行）
        flow.addStretch(1)
        box.setLayout(flow)
        return box

    def _build_tts_group(self, models) -> QWidget:
        box = QGroupBox("语音播报（TTS）")
        form = QFormLayout(box)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("本地 TTS", "local")
        self.mode_combo.addItem("云端 TTS", "cloud")
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(self.prefs.tts_mode)))
        form.addRow("TTS 模式", self.mode_combo)

        # 云端音色（service.list_cloud_speakers() 注入；仅云端模式可选）
        # 首项「默认音色」（data=""）= 未选择，运行时回退 .env 的 TTS_CLOUD_DEFAULT_SPEAKER
        self.speaker_combo = QComboBox()
        self.speaker_combo.addItem("默认音色", "")
        for s in self._speakers:
            self.speaker_combo.addItem(s.display_name, s.speaker_id)
        idx = self.speaker_combo.findData(self.prefs.tts_cloud_speaker)
        if idx >= 0:
            self.speaker_combo.setCurrentIndex(idx)
        form.addRow("云端音色", self.speaker_combo)
        self.mode_combo.currentIndexChanged.connect(self._update_speaker_state)
        self._update_speaker_state()

        self.model_combo = QComboBox()
        for m in models:
            self.model_combo.addItem(self._model_label(m), m.model_id)
        self.model_combo.addItem("系统自带 TTS", "system")
        idx = self.model_combo.findData(self.prefs.tts_local_model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        form.addRow("本地模型", self.model_combo)

        # 下载行：按钮 + 状态提示
        self.download_button = QPushButton("下载")
        self.download_button.clicked.connect(self._on_download_clicked)
        self.download_status = QLabel("")
        dl_row = QHBoxLayout()
        dl_row.addWidget(self.download_button)
        dl_row.addWidget(self.download_status, stretch=1)
        form.addRow("", dl_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        form.addRow("", self.progress_bar)

        self.model_combo.currentIndexChanged.connect(self._update_download_state)
        self._update_download_state()
        self.download_progress.connect(self._on_download_progress)
        self.download_finished.connect(self._on_download_finished)

        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 100000.0)
        self.threshold_spin.setDecimals(2)
        self.threshold_spin.setSuffix(" 元")
        self.threshold_spin.setValue(self.prefs.amount_threshold)
        form.addRow("金额阈值", self.threshold_spin)

        return box

    # ── 模型下载 ──

    def _update_speaker_state(self) -> None:
        """仅云端 TTS 模式下可选音色。"""
        self.speaker_combo.setEnabled(self.mode_combo.currentData() == "cloud")

    def _model_label(self, m) -> str:
        mark = "（已下载）" if m.model_id in self._downloaded else ""
        return f"{m.display_name} {m.size_hint}{mark}"

    def _update_download_state(self) -> None:
        """仅未下载的非系统模型可下载；下载中禁用。"""
        can = (
            self._downloader is not None
            and not self._downloading
            and self.model_combo.currentData() != "system"
            and self.model_combo.currentData() not in self._downloaded
        )
        self.download_button.setEnabled(can)

    def _on_download_clicked(self) -> None:
        model_id = self.model_combo.currentData()
        if model_id == "system":
            return
        self._downloading = True
        self._update_download_state()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.download_status.setText("下载中…")

        def progress(done: int, total: int | None) -> None:
            # 工作线程调用 → 信号转投递到 UI 线程
            self.download_progress.emit(done, total)

        def worker() -> None:
            try:
                self._downloader(model_id, progress)
            except Exception as exc:  # noqa: BLE001 — 下载失败不得中断 UI
                self.download_finished.emit(False, f"下载失败：{exc}")
            else:
                self.download_finished.emit(True, "下载完成")

        threading.Thread(target=worker, name="model-download", daemon=True).start()

    def _on_download_progress(self, done: int, total: int | None) -> None:
        if total:
            self.progress_bar.setValue(min(100, round(done * 100 / total)))

    def _on_download_finished(self, ok: bool, message: str) -> None:
        self._downloading = False
        self.progress_bar.setVisible(False)
        self.download_status.setText(message)
        if ok:
            self._downloaded.add(self.model_combo.currentData())
            idx = self.model_combo.currentIndex()
            text = self.model_combo.itemText(idx)
            if "已下载" not in text:
                self.model_combo.setItemText(idx, f"{text}（已下载）")
        self._update_download_state()

    # ── 写回 ──

    def accept(self) -> None:
        for name, cb in self.switches.items():
            setattr(self.prefs, name, cb.isChecked())
        self.prefs.amount_threshold = self.threshold_spin.value()
        self.prefs.tts_mode = self.mode_combo.currentData()
        self.prefs.tts_local_model = self.model_combo.currentData()
        if self.speaker_combo.currentData() is not None:
            self.prefs.tts_cloud_speaker = self.speaker_combo.currentData()
        if self._save_fn is not None:
            self._save_fn()
        super().accept()
