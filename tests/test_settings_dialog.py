"""设置对话框测试：偏好 ↔ 控件映射、保存写回（rules/02 两层开关）。"""
from config.preferences import Preferences
from ui.settings_dialog import SWITCH_FIELDS


def make_prefs(**kwargs) -> Preferences:
    return Preferences(**kwargs)


def test_dialog_initializes_from_prefs(qtbot):
    prefs = make_prefs(
        broadcast_danmaku=True,
        thanks_gift=True,
        guard_entry_welcome=True,
        amount_threshold=88.0,
        tts_mode="cloud",
        tts_local_model="kokoro-multi-lang-v1_1",
    )
    dialog = _build_dialog(prefs)
    dialog.show()

    assert dialog.switches["broadcast_danmaku"].isChecked() is True
    assert dialog.switches["broadcast_gift"].isChecked() is False
    assert dialog.switches["thanks_gift"].isChecked() is True
    assert dialog.switches["guard_entry_welcome"].isChecked() is True
    assert dialog.threshold_spin.value() == 88.0
    assert dialog.mode_combo.currentData() == "cloud"
    assert dialog.model_combo.currentData() == "kokoro-multi-lang-v1_1"


def test_accept_writes_back_all_fields(qtbot):
    prefs = make_prefs()
    saved = []
    dialog = _build_dialog(prefs, save_fn=lambda: saved.append(1))
    dialog.show()

    # 模拟用户操作：勾选部分开关、改阈值、切模式
    dialog.switches["broadcast_gift"].setChecked(True)
    dialog.switches["thanks_follow"].setChecked(True)
    dialog.threshold_spin.setValue(120.0)
    dialog.mode_combo.setCurrentIndex(1)  # cloud

    dialog.accept()

    assert prefs.broadcast_gift is True
    assert prefs.broadcast_danmaku is False  # 未勾选的保持/写回 False
    assert prefs.thanks_follow is True
    assert prefs.thanks_gift is False
    assert prefs.amount_threshold == 120.0
    assert prefs.tts_mode == "cloud"
    assert saved == [1]


def test_switch_fields_cover_all_rule_02_switches():
    """SWITCH_FIELDS 必须覆盖 rules/02 的 7+4 开关与舰长进场开关。"""
    expected = {
        "broadcast_danmaku", "broadcast_gift", "broadcast_super_chat",
        "broadcast_entry", "broadcast_follow", "broadcast_guard",
        "broadcast_like",
        "thanks_gift", "thanks_super_chat", "thanks_follow", "thanks_guard",
        "guard_entry_welcome",
    }
    assert {name for name, _ in SWITCH_FIELDS} == expected


def _build_dialog(prefs, save_fn=None):
    """构造对话框；模型列表用最小假数据（不含下载流程，见 test_model_download）。"""
    from service.base import ModelInfo

    models = [
        ModelInfo("melo-zh-en", "MeloTTS", "MIT", "约170MB", downloaded=True),
        ModelInfo("kokoro-multi-lang-v1_1", "Kokoro", "Apache-2.0", "约310MB", downloaded=False),
    ]
    from ui.settings_dialog import SettingsDialog

    return SettingsDialog(prefs, save_fn=save_fn, models=models)
