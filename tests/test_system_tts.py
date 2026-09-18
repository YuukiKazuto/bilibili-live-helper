"""系统自带 TTS 后端测试（macOS say / Windows SAPI5 via PowerShell）。"""
import pytest

from tts.local.system_tts import SystemTTSBackend


class FakeRunner:
    """注入式命令执行器：按命令前缀返回预设 stdout。"""

    def __init__(self, outputs: dict[tuple[str, ...] | str, str] | None = None):
        self.outputs = outputs or {}
        self.commands: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> str:
        self.commands.append(cmd)
        joined = " ".join(cmd)
        for key, out in self.outputs.items():
            if (key in joined) if isinstance(key, str) else (" ".join(key) in joined):
                return out
        return ""

    def fail(self, cmd: list[str]) -> None:
        """让下一次执行抛错（模拟命令失败）。"""
        raise RuntimeError(f"命令失败: {cmd}")


MAC_VOICES = (
    # 顺序模拟真实 `say -v ?` 输出：zh_TW 排在 zh_CN 之前
    "Meijia                 zh_TW    # 你好\n"
    "Tingting               zh_CN    # 你好，世界\n"
    "Samantha               en_US    # Hello\n"
)


def test_macos_voice_discovery_picks_chinese():
    backend = SystemTTSBackend(platform="darwin", runner=FakeRunner({("say", "-v", "?"): MAC_VOICES}))
    assert backend.voice == "Tingting"


def test_macos_prefers_zh_cn_over_other_zh_locales():
    """存在 zh_CN 音色时应优先选择（简体中文），而非列表靠前的 zh_TW。"""
    backend = SystemTTSBackend(platform="darwin", runner=FakeRunner({("say", "-v", "?"): MAC_VOICES}))
    # MAC_VOICES 中 Tingting(zh_CN) 与 Meijia(zh_TW) 均可用
    assert backend.voice == "Tingting"


def test_macos_falls_back_to_zh_tw_when_no_zh_cn():
    """没有 zh_CN 时退而选择任意 zh_* 音色。"""
    voices = "Meijia                 zh_TW    # 你好\nSamantha               en_US    # Hello\n"
    backend = SystemTTSBackend(platform="darwin", runner=FakeRunner({("say", "-v", "?"): voices}))
    assert backend.voice == "Meijia"


def test_macos_speak_builds_say_command():
    runner = FakeRunner({("say", "-v", "?"): MAC_VOICES})
    backend = SystemTTSBackend(platform="darwin", runner=runner)
    backend.speak_sync("你好世界")
    assert runner.commands[-1] == ["say", "-v", "Tingting", "--", "你好世界"]


def test_macos_falls_back_to_default_voice_when_no_chinese():
    runner = FakeRunner({("say", "-v", "?"): "Samantha               en_US    # Hello\n"})
    backend = SystemTTSBackend(platform="darwin", runner=runner)
    backend.speak_sync("hello")
    assert runner.commands[-1] == ["say", "--", "hello"]


def test_voice_attribute_lazily_probes():
    """读取 voice 属性应触发懒探测（无需先播报）。"""
    backend = SystemTTSBackend(platform="darwin", runner=FakeRunner({("say", "-v", "?"): MAC_VOICES}))
    assert backend.voice == "Tingting"


def test_windows_picks_chinese_voice_and_builds_powershell_command():
    runner = FakeRunner({
        "GetInstalledVoices": "Microsoft Huihui Desktop|zh-CN\nMicrosoft Zira Desktop|en-US\n",
    })
    backend = SystemTTSBackend(platform="win32", runner=runner)
    backend.speak_sync("你好世界")
    cmd = " ".join(runner.commands[-1])
    assert "powershell" in cmd
    assert "System.Speech" in cmd
    assert "Microsoft Huihui Desktop" in cmd
    assert "你好世界" in cmd


def test_speak_raises_when_command_fails():
    class FailingRunner(FakeRunner):
        def __call__(self, cmd):
            self.commands.append(cmd)
            raise RuntimeError("say: command failed")

    backend = SystemTTSBackend(platform="darwin", runner=FailingRunner())
    with pytest.raises(RuntimeError):
        backend.speak_sync("你好")


def test_unsupported_platform_raises():
    with pytest.raises(RuntimeError):
        SystemTTSBackend(platform="sunos", runner=FakeRunner())
