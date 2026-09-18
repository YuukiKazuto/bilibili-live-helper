"""sherpa-onnx 本地模型 TTS 后端（Apache-2.0 引擎，CPU 实时推理）。

加载 tts/local/model_manager.py 注册表中已下载的模型（MeloTTS / Kokoro），
OfflineTts.generate 离线合成 → sounddevice float32 播放，阻塞至排空，
与云端 TTS 一致满足「一条读完才读下一条」的队列语义。
"""
import logging
import threading
from pathlib import Path

import numpy as np
import sherpa_onnx
import sounddevice as sd

from tts.local.model_manager import LocalModel

logger = logging.getLogger(__name__)


def build_tts_config(model: LocalModel, model_dir: Path) -> sherpa_onnx.OfflineTtsConfig:
    """按注册表配置构造 sherpa-onnx 离线 TTS 配置（路径均为模型目录内相对路径）。"""
    cfg = {
        k: ",".join(str(model_dir / p) for p in v.split(","))
        for k, v in model.config.items()
    }
    model_cfg = sherpa_onnx.OfflineTtsModelConfig(
        num_threads=1,
        provider="cpu",
    )
    if model.engine == "vits":
        model_cfg.vits = sherpa_onnx.OfflineTtsVitsModelConfig(
            model=cfg["model"],
            lexicon=cfg.get("lexicon", ""),
            tokens=cfg["tokens"],
            dict_dir=cfg.get("dict_dir", ""),
        )
    elif model.engine == "kokoro":
        model_cfg.kokoro = sherpa_onnx.OfflineTtsKokoroModelConfig(
            model=cfg["model"],
            voices=cfg["voices"],
            tokens=cfg["tokens"],
            lexicon=cfg.get("lexicon", ""),
            data_dir=cfg.get("data_dir", ""),
            dict_dir=cfg.get("dict_dir", ""),
        )
    else:
        raise RuntimeError(f"不支持的引擎类型: {model.engine}")
    return sherpa_onnx.OfflineTtsConfig(
        model=model_cfg,
        rule_fsts=cfg.get("rule_fsts", ""),
    )


class Float32PcmPlayer:
    """sounddevice float32 播放器：write 边播边写，drain 等待排空。"""

    def __init__(self, sample_rate: int) -> None:
        self._stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
        )
        self._stream.start()

    def write(self, samples: np.ndarray) -> None:
        self._stream.write(samples)

    def drain(self) -> None:
        self._stream.stop()  # 播完缓冲区剩余音频后才返回

    def close(self) -> None:
        self._stream.close()


class SherpaTTSBackend:
    """sherpa-onnx 离线 TTS 后端。speak_sync 为同步阻塞，由 LocalTTS 调度到线程池。"""

    def __init__(
        self,
        model: LocalModel,
        model_dir: Path,
        *,
        engine_factory=None,
        player_factory=Float32PcmPlayer,
    ) -> None:
        self.model = model
        self.model_dir = Path(model_dir)
        self._engine_factory = engine_factory or (lambda cfg: sherpa_onnx.OfflineTts(cfg))
        self._player_factory = player_factory
        self._engine = None
        self._engine_lock = threading.Lock()

    @property
    def engine(self):
        """懒加载推理引擎（模型加载需数秒，首次播报时创建一次）。"""
        with self._engine_lock:
            if self._engine is None:
                config = build_tts_config(self.model, self.model_dir)
                self._engine = self._engine_factory(config)
            return self._engine

    def speak_sync(self, text: str, speaker_id: int = 0, speed: float = 1.0) -> None:
        """合成并播放一段文本，阻塞至播放排空。"""
        audio = self.engine.generate(text, sid=speaker_id, speed=speed)
        player = self._player_factory(audio.sample_rate)
        try:
            # sherpa 实测返回 float64，播放流要求 float32
            samples = np.asarray(audio.samples, dtype=np.float32)
            player.write(samples)
            player.drain()
        finally:
            player.close()
