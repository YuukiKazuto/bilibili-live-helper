"""service 层测试：生命周期、事件分发、偏好、模型管理。"""
import asyncio
import time

import pytest

import service.local as service_local
from config.loader import Settings
from config.preferences import Preferences
from platforms.base import LiveEvent
from service.base import ServiceError
from service.local import LocalLiveService


class FakePlatform:
    """测试替身：connect 后注入一条事件，然后保持运行直到被取消。"""

    instances: list["FakePlatform"] = []

    def __init__(self, settings, id_code, on_event):
        self.settings = settings
        self.id_code = id_code
        self.on_event = on_event
        self.connected = False
        self.closed = False
        FakePlatform.instances.append(self)

    async def connect(self):
        self.connected = True

    async def run(self):
        await self.on_event(
            LiveEvent(type="danmaku", user_name="测试用户", content="你好")
        )
        await asyncio.Event().wait()  # 挂起直至 stop 取消

    async def close(self):
        self.closed = True


@pytest.fixture()
def fake_platform_cls(monkeypatch):
    monkeypatch.setattr(service_local, "BilibiliLiveClient", FakePlatform)
    FakePlatform.instances.clear()
    return FakePlatform


def make_service(**prefs_kwargs) -> LocalLiveService:
    prefs_kwargs.setdefault("bili_id_code", "CODE123")
    return LocalLiveService(
        settings=Settings(),
        prefs=Preferences(**prefs_kwargs),
    )


def wait_until(cond, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_start_stop_lifecycle(fake_platform_cls):
    service = make_service()
    service.start()
    assert service.is_running()
    assert wait_until(lambda: fake_platform_cls.instances), "平台未创建"
    platform = fake_platform_cls.instances[-1]
    assert wait_until(lambda: platform.connected)
    assert platform.id_code == "CODE123"

    service.stop()
    assert platform.closed
    assert not service.is_running()

    # 幂等：重复 stop 不报错
    service.stop()


def test_missing_id_code_raises(fake_platform_cls):
    service = make_service(bili_id_code="")
    with pytest.raises(ServiceError, match="身份码"):
        service.start()
    assert not service.is_running()


def test_double_start_raises(fake_platform_cls):
    service = make_service()
    service.start()
    try:
        assert wait_until(lambda: fake_platform_cls.instances)
        with pytest.raises(ServiceError, match="已在运行"):
            service.start()
    finally:
        service.stop()


def test_unsubscribe(fake_platform_cls):
    service = make_service()
    received: list[LiveEvent] = []
    cb = received.append

    service.subscribe_events(cb)
    service.unsubscribe_events(cb)
    service.start()
    try:
        assert wait_until(lambda: fake_platform_cls.instances)
        time.sleep(0.1)
        assert not received
    finally:
        service.stop()


def test_events_forwarded_to_subscribers(fake_platform_cls):
    service = make_service()
    received: list[LiveEvent] = []

    def on_event(event):
        received.append(event)

    service.subscribe_events(on_event)
    service.start()
    try:
        assert wait_until(lambda: len(received) >= 1), "事件未转发到订阅者"
        assert received[0].type == "danmaku"
        assert received[0].user_name == "测试用户"
    finally:
        service.stop()


def test_save_preferences(fake_platform_cls, monkeypatch):
    saved = []
    monkeypatch.setattr(
        service_local.PreferenceStore, "save", lambda prefs, path=None: saved.append(prefs)
    )
    service = make_service()
    prefs = service.get_preferences()
    prefs.amount_threshold = 88.0
    service.save_preferences()
    assert saved == [prefs]
    assert saved[0].amount_threshold == 88.0


def test_warnings(fake_platform_cls):
    # 云端模式 + 密钥缺失 + B站密钥缺失
    service = make_service(tts_mode="cloud")
    warns = service.warnings()
    assert any("TTS_CLOUD_API_KEY" in w for w in warns)
    assert any("bili_app_id" in w for w in warns)


def test_list_models(fake_platform_cls):
    service = make_service()
    models = service.list_models()
    assert len(models) == 2
    ids = {m.model_id for m in models}
    assert ids == {"vits-melo-tts-zh_en", "kokoro-multi-lang-v1_1"}
    # downloaded 与本机实际下载状态一致（开发机 models/ 可能已有模型）
    from tts.local.model_manager import resolve_models_dir
    from tts.local.model_manager import ModelManager
    manager = ModelManager(resolve_models_dir(service.get_preferences().models_dir))
    for m in models:
        expected = manager.is_downloaded(
            next(x for x in service_local.AVAILABLE_MODELS if x.model_id == m.model_id)
        )
        assert m.downloaded == expected


async def test_download_model_unknown(fake_platform_cls):
    service = make_service()
    with pytest.raises(ServiceError, match="未知模型"):
        await service.download_model("no-such-model")


def test_platform_crash_exits_cleanly():
    """平台以真实异常退出（如长连 keepalive 超时）时服务正常收尾，不炸事件循环。

    现场复现（2026-09-19）：websockets ConnectionClosedError 穿透
    `await platform_task`（原实现只 suppress CancelledError）导致
    「[服务] 事件循环异常退出」+ 完整堆栈。
    """
    class DyingPlatform(FakePlatform):
        async def run(self):
            await self.on_event(LiveEvent(type="danmaku", user_name="A", content="hi"))
            raise RuntimeError("simulated ConnectionClosedError")

    service = LocalLiveService(
        settings=Settings(),
        prefs=Preferences(bili_id_code="CODE123"),
        platform_factory=lambda s, c, cb: DyingPlatform(s, c, cb),
    )
    # 原实现此处会抛 RuntimeError；修复后应正常返回
    asyncio.run(service._run())
    assert not service.is_running()


async def test_client_close_swallows_ws_close_timeout():
    """close 时 ws 关闭握手超时（现场实测 TimeoutError）不应向上抛。"""
    class BoomWS:
        async def close(self):
            raise TimeoutError("timed out while closing connection")

    from platforms.bilibili.client import BilibiliLiveClient

    client = BilibiliLiveClient(settings=Settings(), id_code="c", on_event=None)
    client._ws = BoomWS()
    await client.close()  # 不抛即通过


async def test_connect_disables_protocol_ping(fake_platform_cls):
    """B站 comet 服务器不回复协议层 PING（实测），必须禁用 websockets
    内建 keepalive，长连保活靠 B站自有的 op=2 应用层心跳。"""
    import json

    import platforms.bilibili.client as client_mod
    from platforms.bilibili.client import BilibiliLiveClient
    from platforms.bilibili.proto import Proto, OP_AUTH_REPLY

    captured_kwargs: dict = {}

    def auth_reply_frame() -> bytes:
        p = Proto()
        p.op = OP_AUTH_REPLY
        p.body = json.dumps({"code": 0}).encode()
        return p.pack()

    class FakeWS:
        async def send(self, data):
            pass

        async def recv(self):
            return auth_reply_frame()

    async def fake_connect(addr, **kwargs):
        captured_kwargs.update(kwargs)
        return FakeWS()

    async def fake_post(self, path, params):
        assert path == "/v2/app/start"
        return {
            "game_info": {"game_id": "g1"},
            "websocket_info": {"wss_link": ["wss://fake"], "auth_body": "b"},
        }

    client = BilibiliLiveClient(settings=Settings(), id_code="c", on_event=None)
    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(client_mod.websockets, "connect", fake_connect)
        monkey.setattr(BilibiliLiveClient, "_post", fake_post)
        await client.connect()
    finally:
        monkey.undo()
    assert "ping_interval" in captured_kwargs and captured_kwargs["ping_interval"] is None
    # B站也不回复 close 握手（实测挂满默认 10s 才关闭），须缩短 close_timeout
    assert "close_timeout" in captured_kwargs and captured_kwargs["close_timeout"] <= 2
    # 清理资源（避免测试泄漏会话）
    client.game_id = ""
    client._ws = None
    if client._session is not None:
        await client._session.close()
