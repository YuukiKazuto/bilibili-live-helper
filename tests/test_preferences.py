"""用户偏好持久化测试（本地 TTS 相关字段）。"""
from config.preferences import PreferenceStore


def test_tts_local_model_defaults_to_system():
    prefs = PreferenceStore.load()
    assert prefs.tts_local_model == "system"


def test_tts_local_model_roundtrip(tmp_path):
    path = tmp_path / "prefs.json"
    prefs = PreferenceStore.load(path)
    prefs.tts_local_model = "kokoro-multi-lang-v1_1"
    PreferenceStore.save(prefs, path)

    loaded = PreferenceStore.load(path)
    assert loaded.tts_local_model == "kokoro-multi-lang-v1_1"
