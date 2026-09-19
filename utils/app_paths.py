"""应用根目录解析（源码运行 / PyInstaller 打包通用）。

PyInstaller 冻结后 `__file__` 指向包内临时解压目录，不能再用它定位
应用旁边的文件（.env / config.json / user_preferences.json）——
必须检测 sys.frozen 后改用 exe 所在目录（rules/03 分发与打包）。
"""
import sys
from pathlib import Path


def app_root() -> Path:
    """应用根目录：源码运行 = 项目根；打包运行 = exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent
