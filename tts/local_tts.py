"""本地 TTS：路由器 + 后端注册。

- 默认系统自带 TTS（tts/local/system_tts.py，零下载开箱即用）
- 可下载模型（tts/local/model_manager.py 注册表，MIT / Apache-2.0 免费可商用）
  下载后经 sherpa-onnx 推理（tts/local/sherpa_tts.py）
- 模型未下载 / 引擎缺失时回退系统 TTS，记日志明确提示，不中断播报循环
（设计见 .claude/rules/04-tts.md）
"""
import asyncio
import logging

from tts.base import TTSProvider
from tts.local.model_manager import MODELS_DIR, ModelManager, find_model
from tts.local.sherpa_tts import SherpaTTSBackend
from tts.local.system_tts import SystemTTSBackend

logger = logging.getLogger(__name__)


class LocalTTS(TTSProvider):
    """本地 TTS 实现：按 tts_local_model 偏好在系统后端与 sherpa 模型后端间路由。"""

    def __init__(
        self,
        settings,
        local_model: str = "system",
        *,
        models_dir=MODELS_DIR,
        system_backend: SystemTTSBackend | None = None,
        sherpa_backend_factory=None,
    ) -> None:
        self.settings = settings
        self._local_model_id = local_model or "system"
        self._manager = ModelManager(models_dir)
        self._system_backend = system_backend or SystemTTSBackend()
        self._sherpa_factory = sherpa_backend_factory or (
            lambda model, model_dir: SherpaTTSBackend(model, model_dir)
        )
        self._resolved = None  # 懒解析，首次播报时确定后端

    async def speak(self, text: str) -> None:
        """合成并播放一段文本（阻塞至播放完成，保证播报顺序）。"""
        backend = self._resolve_backend()
        try:
            await asyncio.to_thread(backend.speak_sync, text)
        except Exception:  # noqa: BLE001 — 单条播报失败不中断播报循环
            logger.exception("[本地TTS] 播报失败，跳过: %s", text)

    async def close(self) -> None:
        backend = self._resolved or self._system_backend
        close = getattr(backend, "close", None)
        if close is not None:
            await asyncio.to_thread(close)

    # ── 内部实现 ──

    def _resolve_backend(self):
        """确定实际后端：模型已下载 → sherpa 后端；否则回退系统 TTS。"""
        if self._resolved is not None:
            return self._resolved

        if self._local_model_id != "system":
            model = find_model(self._local_model_id)
            if model is None:
                logger.warning("[本地TTS] 未知模型 %r，回退系统 TTS", self._local_model_id)
            elif not self._manager.is_downloaded(model):
                logger.warning(
                    "[本地TTS] 模型 %s 未下载，回退系统 TTS（可在 UI 重新选择或下载）",
                    model.model_id,
                )
            else:
                self._resolved = self._sherpa_factory(model, self._manager.model_dir(model))
                return self._resolved
        self._resolved = self._system_backend
        return self._resolved
