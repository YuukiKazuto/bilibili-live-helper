"""系统自带 TTS 后端：零下载默认方案。

- macOS：`say` 命令，自动发现 zh_* 系统中文音色（如 Tingting）
- Windows：SAPI5 via PowerShell System.Speech，自动选择已安装中文语音（如 Huihui）

speak_sync 阻塞至播报完成（子进程退出），由 LocalTTS 在线程池中调用，
保证播报队列「一条读完才读下一条」的语义（见 .claude/rules/02-features.md）。
"""
import logging
import platform as _platform
import subprocess

logger = logging.getLogger(__name__)

Runner = callable  # type: annotate — cmd(list[str]) -> stdout(str)，非零退出抛 RuntimeError


def _default_runner(cmd: list[str]) -> str:
    """执行命令并返回 stdout；非零退出码抛 RuntimeError。"""
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"命令失败({proc.returncode}): {' '.join(cmd)}\n{proc.stderr}")
    return proc.stdout


class SystemTTSBackend:
    """操作系统自带 TTS：macOS say / Windows SAPI5。"""

    def __init__(self, platform: str | None = None, runner: Runner | None = None) -> None:
        self._platform = platform or _platform.system().lower()
        # darwin → macOS；windows → win32
        if self._platform == "darwin":
            self._os = "macos"
        elif self._platform in ("windows", "win32"):
            self._os = "windows"
        else:
            raise RuntimeError(f"系统自带 TTS 暂不支持该平台: {self._platform}")
        self._runner = runner or _default_runner
        self._voice: str | None = None  # 懒发现（首次访问时探测中文音色）
        self._voice_probed = False

    @property
    def voice(self) -> str | None:
        """发现的中文音色名；未找到为 None（用系统默认）。"""
        self._probe_voice()
        return self._voice

    def speak_sync(self, text: str) -> None:
        """合成并播放一段文本，阻塞至播放完成。"""
        if self._os == "macos":
            cmd = ["say"]
            if self.voice:
                cmd += ["-v", self.voice]
            cmd += ["--", text]
        else:
            cmd = ["powershell", "-NoProfile", "-Command", self._win_script(text)]
        self._runner(cmd)

    # ── 内部实现 ──

    def _probe_voice(self) -> None:
        """首次访问时发现系统中文音色；找不到则用系统默认（记日志）。"""
        if self._voice_probed:
            return
        self._voice_probed = True
        try:
            if self._os == "macos":
                stdout = self._runner(["say", "-v", "?"])
                fallback: str | None = None
                for line in stdout.splitlines():
                    parts = line.split()
                    # 行格式：`Tingting               zh_CN    # 你好，世界`
                    if len(parts) < 2:
                        continue
                    locale = parts[1].lower()
                    if not locale.startswith("zh"):
                        continue
                    if locale == "zh_cn":
                        # 优先简体中文（zh_TW 等列在前也不选）
                        self._voice = parts[0]
                        break
                    fallback = fallback or parts[0]
                if self._voice is None:
                    self._voice = fallback
            else:
                # 按 Culture（如 zh-CN）匹配，语音名本身不含 "zh"（如 Huihui/Kangkang）
                stdout = self._runner([
                    "powershell", "-NoProfile", "-Command",
                    "Add-Type -AssemblyName System.Speech; "
                    "(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
                    '.GetInstalledVoices() | ForEach-Object { "$($_.VoiceInfo.Name)|$($_.VoiceInfo.Culture.Name)" }',
                ])
                for line in stdout.splitlines():
                    name, _, culture = line.strip().partition("|")
                    if name and culture.lower().startswith("zh"):
                        self._voice = name
                        break
        except Exception:  # noqa: BLE001 — 音色探测失败不阻塞播报
            logger.warning("[本地TTS] 中文音色探测失败，使用系统默认音色", exc_info=True)
        if not self._voice:
            logger.warning("[本地TTS] 未找到系统中文音色，使用系统默认音色")

    def _win_script(self, text: str) -> str:
        """构造 PowerShell 播报脚本（文本中的单引号需翻倍转义）。"""
        safe = text.replace("'", "''")
        select = f"$s.SelectVoice('{self.voice}'); " if self.voice else ""
        return (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"{select}$s.Speak('{safe}')"
        )
