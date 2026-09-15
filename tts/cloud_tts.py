"""云端 TTS。

规则（.claude/rules/04-tts.md）：
- API 密钥只从项目配置文件读取，不读取系统环境变量（由 loader 传入 settings）。
- 密钥缺失时给出明确提示，不得静默失败或回退读系统环境变量。
- 预留订阅制计费接口（阶段 2 H5 插件上线后云端 TTS 订阅收费）。
"""
import logging

from tts.base import TTSProvider

logger = logging.getLogger(__name__)


class CloudTTS(TTSProvider):
    """云端 TTS 实现（骨架：请求/播放待接入）。"""

    def __init__(self, settings) -> None:
        self.settings = settings
        if not settings.tts_cloud_api_key:
            # 明确提示密钥缺失（UI 层据此展示配置引导）
            logger.warning("云端 TTS 密钥未配置，请在项目配置文件中填写 TTS_CLOUD_API_KEY")

    async def speak(self, text: str) -> None:
        if not self.settings.tts_cloud_api_key:
            logger.error("[云端TTS] 密钥缺失，跳过播报: %s", text)
            return
        # TODO: 调用云端 TTS API 合成 + 播放
        await self._charge_hook(text)

    async def _charge_hook(self, text: str) -> None:
        """订阅制计费钩子（阶段 2 预留：订阅态校验、用量上报）。"""

    async def close(self) -> None:
        pass
