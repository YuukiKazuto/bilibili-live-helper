"""本地 TTS：支持下载高质量本地语音模型。

模型下载来源需评估合法性与可用性（许可允许商用/分发）后接入；
模型文件目录不入 Git（见 .claude/rules/04-tts.md）。
"""
import logging

from tts.base import TTSProvider

logger = logging.getLogger(__name__)


class LocalTTS(TTSProvider):
    """本地 TTS 实现（骨架：模型下载与推理待接入）。"""

    def __init__(self, settings) -> None:
        self.settings = settings
        # TODO: 初始化本地语音模型（下载/加载）

    async def speak(self, text: str) -> None:
        # TODO: 本地合成 + 播放；当前仅日志占位
        logger.info("[本地TTS] %s", text)

    async def close(self) -> None:
        pass
