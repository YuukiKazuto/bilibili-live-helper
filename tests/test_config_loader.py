"""配置加载回归测试：默认 API host 必须是可解析的线上域名（rules/05 以官方文档为准）。"""
from config.loader import Settings


def test_default_api_host_is_resolvable_documented_host():
    """live-open.biliapi.net 无法 DNS 解析（2026-09-19 实测），demo 与线上均用 .com。"""
    assert Settings.bili_api_host == "https://live-open.biliapi.com"
