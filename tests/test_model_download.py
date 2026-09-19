"""设置对话框模型下载流程测试：进度跨线程投递、完成后刷新状态。"""
import threading
import time

from config.preferences import Preferences
from service.base import ModelInfo
from ui.settings_dialog import SettingsDialog


MODELS = [
    ModelInfo("kokoro", "Kokoro", "Apache-2.0", "约310MB", downloaded=False),
    ModelInfo("melo", "MeloTTS", "MIT", "约170MB", downloaded=True),
]


def make_dialog(downloader) -> SettingsDialog:
    prefs = Preferences(tts_local_model="kokoro")
    return SettingsDialog(prefs, save_fn=None, models=MODELS, downloader=downloader)


def test_download_button_enabled_only_for_undownloaded_model(qtbot):
    dialog = make_dialog(downloader=lambda *_: None)
    dialog.show()

    assert dialog.model_combo.currentData() == "kokoro"  # 未下载 → 可下载
    assert dialog.download_button.isEnabled()

    dialog.model_combo.setCurrentIndex(dialog.model_combo.findData("melo"))
    assert not dialog.download_button.isEnabled()  # 已下载 → 禁用

    dialog.model_combo.setCurrentIndex(dialog.model_combo.findData("system"))
    assert not dialog.download_button.isEnabled()  # 系统 TTS 无需下载


def test_download_reports_progress_and_finishes(qtbot):
    """点下载：downloader 收到模型 id，进度更新进度条，完成后按钮恢复。"""
    started = threading.Event()

    def fake_downloader(model_id, progress):
        started.set()
        progress(40, 100)
        progress(100, 100)

    dialog = make_dialog(fake_downloader)
    dialog.show()

    dialog.download_button.click()
    qtbot.waitUntil(started.is_set, timeout=2000)

    # 进度经 Qt 信号投递到 UI 线程（rules/07 跨线程投递）
    qtbot.waitUntil(lambda: dialog.progress_bar.value() == 100, timeout=2000)
    # 下载完成：状态提示更新；模型已标记下载 → 按钮禁用（与既有规则一致）
    qtbot.waitUntil(lambda: "完成" in dialog.download_status.text(), timeout=2000)
    assert not dialog.download_button.isEnabled()
    assert "已下载" in dialog.model_combo.currentText()


def test_download_failure_shows_error_not_crash(qtbot):
    """下载异常：状态栏提示失败，按钮恢复，不中断 UI。"""
    def bad_downloader(model_id, progress):
        raise RuntimeError("网络错误")

    dialog = make_dialog(bad_downloader)
    dialog.show()

    dialog.download_button.click()
    qtbot.waitUntil(lambda: "失败" in dialog.download_status.text(), timeout=2000)
    assert dialog.download_button.isEnabled()
