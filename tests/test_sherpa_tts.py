"""sherpa-onnx 本地模型 TTS 后端测试。"""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from sherpa_onnx import (
    OfflineTtsConfig,
    OfflineTtsKokoroModelConfig,
    OfflineTtsModelConfig,
    OfflineTtsVitsModelConfig,
)

from tts.local.model_manager import find_model
from tts.local.sherpa_tts import SherpaTTSBackend, build_tts_config


class FakeEngine:
    """注入式 sherpa 引擎：记录 generate 调用，返回固定音频。"""

    def __init__(self, sample_rate: int = 24000):
        self.sample_rate = sample_rate
        self.calls: list[dict] = []

    def generate(self, text: str, sid: int = 0, speed: float = 1.0):
        self.calls.append({"text": text, "sid": sid, "speed": speed})
        # 真实 sherpa 返回 float64（实测），播放器要求 float32
        return SimpleNamespace(
            samples=np.zeros(100, dtype=np.float64), sample_rate=self.sample_rate
        )


class FakePlayer:
    """注入式播放器：记录生命周期事件。"""

    def __init__(self, sample_rate: int, events: list):
        self.sample_rate = sample_rate
        self._events = events

    def write(self, samples) -> None:
        self._events.append(("write", samples.shape, samples.dtype))

    def drain(self) -> None:
        self._events.append(("drain",))

    def close(self) -> None:
        self._events.append(("close",))


# ── 配置构造 ──


def test_build_vits_config_from_melo_model(tmp_path):
    melo = find_model("vits-melo-tts-zh_en")
    cfg = build_tts_config(melo, tmp_path)
    assert isinstance(cfg.model.vits, OfflineTtsVitsModelConfig)
    assert cfg.model.vits.model == str(tmp_path / "model.onnx")
    assert cfg.model.vits.lexicon == str(tmp_path / "lexicon.txt")
    assert cfg.model.vits.tokens == str(tmp_path / "tokens.txt")
    assert cfg.model.vits.dict_dir == str(tmp_path / "dict")
    assert cfg.rule_fsts == ",".join(str(tmp_path / f) for f in
                                     ["date.fst", "number.fst", "phone.fst", "new_heteronym.fst"])


def test_build_kokoro_config(tmp_path):
    kokoro = find_model("kokoro-multi-lang-v1_1")
    cfg = build_tts_config(kokoro, tmp_path)
    assert isinstance(cfg.model.kokoro, OfflineTtsKokoroModelConfig)
    assert cfg.model.kokoro.model == str(tmp_path / "model.onnx")
    assert cfg.model.kokoro.voices == str(tmp_path / "voices.bin")
    assert cfg.model.kokoro.lexicon == str(tmp_path / "lexicon-zh.txt")
    assert cfg.model.kokoro.data_dir == str(tmp_path / "espeak-ng-data")
    assert cfg.model.kokoro.dict_dir == str(tmp_path / "dict")


# ── 合成与播放 ──


def test_speak_generates_and_plays_with_player_lifecycle(tmp_path):
    events: list = []
    engine_holder: list[FakeEngine] = []

    def engine_factory(cfg: OfflineTtsConfig) -> FakeEngine:
        e = FakeEngine(sample_rate=24000)
        engine_holder.append(e)
        return e

    def player_factory(sample_rate: int) -> FakePlayer:
        events.append(("create", sample_rate))
        return FakePlayer(sample_rate, events)

    melo = find_model("vits-melo-tts-zh_en")
    backend = SherpaTTSBackend(
        melo, tmp_path, engine_factory=engine_factory, player_factory=player_factory
    )
    backend.speak_sync("你好", speaker_id=2)

    assert engine_holder[0].calls == [{"text": "你好", "sid": 2, "speed": 1.0}]
    # 生命周期：创建（带采样率）→ 写入（float64 样本已转 float32）→ 排空 → 关闭
    assert events == [
        ("create", 24000),
        ("write", (100,), np.dtype("float32")),
        ("drain",),
        ("close",),
    ]


def test_engine_created_lazily_once(tmp_path):
    """引擎应首次播报时创建且只创建一次（模型加载开销大）。"""
    calls: list[int] = []

    def engine_factory(cfg: OfflineTtsConfig) -> FakeEngine:
        calls.append(1)
        return FakeEngine()

    kokoro = find_model("kokoro-multi-lang-v1_1")
    backend = SherpaTTSBackend(
        kokoro, tmp_path, engine_factory=engine_factory,
        player_factory=lambda sr: FakePlayer(sr, []),
    )
    backend.speak_sync("一")
    backend.speak_sync("二")
    assert calls == [1]
