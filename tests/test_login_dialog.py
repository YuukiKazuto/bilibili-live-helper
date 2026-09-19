"""登录对话框测试：身份码写入偏好 + 保存回调（rules/03「主播身份码例外」）。"""
from config.preferences import Preferences
from ui.login_dialog import LoginDialog, need_login


def test_need_login_when_code_empty():
    assert need_login(Preferences(bili_id_code="")) is True
    assert need_login(Preferences(bili_id_code="CODE123")) is False


def test_login_dialog_writes_prefs_and_calls_save(qtbot):
    prefs = Preferences(bili_id_code="")
    saved = []
    dialog = LoginDialog(prefs, save_fn=lambda: saved.append(1))
    dialog.show()

    dialog.code_edit.setText("  MY_CODE  ")
    dialog.save_button.click()

    assert prefs.bili_id_code == "MY_CODE"  # 去除首尾空白
    assert saved == [1]  # save_preferences 被调用
    assert dialog.result() == dialog.DialogCode.Accepted


def test_login_dialog_empty_code_rejected(qtbot):
    """空身份码点击保存：不写入、不关闭，提示重新输入。"""
    prefs = Preferences(bili_id_code="")
    saved = []
    dialog = LoginDialog(prefs, save_fn=lambda: saved.append(1))
    dialog.show()

    dialog.code_edit.setText("   ")
    dialog.save_button.click()

    assert prefs.bili_id_code == ""
    assert saved == []
    assert dialog.result() != dialog.DialogCode.Accepted
