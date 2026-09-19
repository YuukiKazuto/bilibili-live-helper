"""配置加载回归测试：默认 API host 必须是可解析的线上域名（rules/05 以官方文档为准）。"""
from config.loader import Settings


def test_default_api_host_is_resolvable_documented_host():
    """live-open.biliapi.net 无法 DNS 解析（2026-09-19 实测），demo 与线上均用 .com。"""
    assert Settings.bili_api_host == "https://live-open.biliapi.com"


# ── 冻结模式（PyInstaller 打包）路径解析 ──


def test_app_root_source_mode_is_project_root():
    """源码运行：应用根 = 项目根（能找到 main.py）。"""
    import sys
    import importlib
    from utils import app_paths

    importlib.reload(app_paths)  # 清除其他用例可能残留的 monkeypatch
    assert (app_paths.app_root() / "main.py").exists()


def test_app_root_frozen_uses_exe_dir(monkeypatch, tmp_path):
    """PyInstaller 冻结运行：应用根 = exe 所在目录（sys.frozen=True）。"""
    import sys
    from utils.app_paths import app_root

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app.exe"))
    assert app_root() == tmp_path


def test_load_settings_reads_env_next_to_exe(monkeypatch, tmp_path):
    """打包后 .env 必须从 exe 同目录读取（原实现指向源码目录，exe 读不到密钥）。"""
    import sys
    import config.loader as cl

    (tmp_path / ".env").write_text("BILI_APP_ID=12345\n", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app.exe"))

    settings = cl.load_settings()
    assert settings.bili_app_id == 12345
