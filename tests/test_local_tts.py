"""LocalTTS 路由器测试：系统自带 TTS 默认、可下载模型分发、失败回退。"""
import logging
from pathlib import Path

import pytest

from tts.local_tts import LocalTTS


class FakeSettings:
    pass


class FakeBackend:
    """通用假后端：记录调用。"""

    def __init__(self, name: str):
        self.name = name
        self.spoken: list[str] = []
        self.closed = False

    def speak_sync(self, text: str, **kwargs) -> None:
        self.spoken.append(text)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def system_backend():
    return FakeBackend("system")


def make_tts(local_model="system", system_backend=None, downloaded=False, models_dir=None):
    created = []

    def sherpa_factory(model, model_dir: Path):
        b = FakeBackend(f"sherpa:{model.model_id}")
        created.append(b)
        return b

    kwargs = {"system_backend": system_backend, "sherpa_backend_factory": sherpa_factory}
    if models_dir is not None:
        kwargs["models_dir"] = models_dir

    tts = LocalTTS(FakeSettings(), local_model=local_model, **kwargs)
    return tts, created


# ── 默认：系统自带 TTS ──


def test_default_routes_to_system_backend(system_backend):
    tts, created = make_tts(system_backend=system_backend)
    import asyncio

    asyncio.run(tts.speak("你好"))
    assert system_backend.spoken == ["你好"]
    assert created == []


def test_unknown_model_id_falls_back_to_system(system_backend, caplog):
    tts, created = make_tts(local_model="no-such-model", system_backend=system_backend)
    import asyncio

    with caplog.at_level(logging.WARNING):
        asyncio.run(tts.speak("你好"))
    assert system_backend.spoken == ["你好"]
    assert created == []


# ── 已下载模型：走 sherpa 后端 ──


def test_downloaded_model_routes_to_sherpa_backend(system_backend):
    import asyncio
    from tts.local.model_manager import find_model, AVAILABLE_MODELS

    # 在假模型目录中放入必需文件，视为已下载
    models_dir = Path("/tmp") / "fake-models-downloaded"
    model = find_model("vits-melo-tts-zh_en")
    d = models_dir / model.model_id
    d.mkdir(parents=True, exist_ok=True)
    for rel in model.required_files:
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")

    tts, created = make_tts(
        local_model=model.model_id,
        system_backend=system_backend,
        models_dir=models_dir,
    )
    asyncio.run(tts.speak("你好"))

    assert created and created[0].spoken == ["你好"]
    assert system_backend.spoken == []


# ── 未下载模型：回退系统 TTS ──


def test_not_downloaded_model_falls_back_to_system(system_backend, caplog):
    import asyncio
    from tts.local.model_manager import find_model

    models_dir = Path("/tmp") / "fake-models-empty"

    with caplog.at_level(logging.WARNING):
        tts, created = make_tts(
            local_model=find_model("kokoro-multi-lang-v1_1").model_id,
            system_backend=system_backend,
            models_dir=models_dir,
        )
        asyncio.run(tts.speak("你好"))

    assert system_backend.spoken == ["你好"]
    assert created == []
    assert any("回退" in r.message or "未下载" in r.message for r in caplog.records)


def test_close_closes_active_backend(system_backend):
    import asyncio

    tts, created = make_tts(system_backend=system_backend)
    asyncio.run(tts.speak("你好"))
    asyncio.run(tts.close())
    assert system_backend.closed
