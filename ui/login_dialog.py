"""登录对话框：主播身份码填写 + 保存（rules/03「主播身份码例外」）。

身份码是运行时凭证而非密钥：UI 填写后随用户偏好持久化，下次打开自动填充。
登录成功后主窗口不再出现身份码入口（产品决策：need_login 为唯一入口判断）。
"""
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from config.preferences import Preferences


def need_login(prefs: Preferences) -> bool:
    """是否需要弹出登录：身份码为空即需要。"""
    return not prefs.bili_id_code


class LoginDialog(QDialog):
    """首次使用时的身份码登录窗（模态，关闭前不进主界面）。"""

    def __init__(self, prefs: Preferences, save_fn, parent=None) -> None:
        """save_fn: 持久化回调（阶段 1 传 service.save_preferences）。"""
        super().__init__(parent)
        self.prefs = prefs
        self._save_fn = save_fn
        self.setWindowTitle("登录 B站直播间")
        self.setModal(True)

        hint = QLabel("请输入主播身份码（保存后自动填充，无需重复输入）")
        hint.setWordWrap(True)

        self.code_edit = QLineEdit()
        self.code_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.code_edit.setPlaceholderText("主播身份码")

        # 行内错误提示（避免模态弹窗打断输入）
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #d33;")
        self.error_label.setWordWrap(True)

        self.save_button = QPushButton("保存并连接")
        self.save_button.setDefault(True)

        form = QFormLayout()
        form.addRow("", self.code_edit)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addWidget(self.save_button)
        self.save_button.clicked.connect(self._on_save)
        self.code_edit.returnPressed.connect(self._on_save)

    def _on_save(self) -> None:
        code = self.code_edit.text().strip()
        if not code:
            self.error_label.setText("身份码不能为空，请重新输入")
            self.code_edit.setFocus()
            return
        self.prefs.bili_id_code = code
        self._save_fn()
        self.accept()
