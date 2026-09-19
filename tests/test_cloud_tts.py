"""火山引擎云端 TTS 协议层测试。

覆盖（接入规范见 .claude/rules/06-volcengine-tts.md，协议见 tts/volcengine_proto.py）：
- 请求头 / 请求体构造
- 二进制帧编解码（FullClientRequest / AudioOnlyServer 事件帧 / SessionFinished / Error）
- speak 全流程（fake WebSocket + fake 播放器，不触网不发声）
- 密钥缺失提示、连接失败与服务端错误的容错、计费用量上报
"""
import json
import struct

import pytest

from tts.cloud_tts import CloudTTS, build_headers, build_request_payload
from tts.volcengine_proto import (
    EVENT_SESSION_FAILED,
    EVENT_SESSION_FINISHED,
    EVENT_TTS_RESPONSE,
    EVENT_USAGE_RESPONSE,
    FLAG_WITH_EVENT,
    MSG_AUDIO_ONLY_SERVER,
    MSG_ERROR,
    MSG_FULL_CLIENT_REQUEST,
    MSG_FULL_SERVER_RESPONSE,
    decode_frame,
    encode_frame,
    encode_full_client_request,
)

SESSION = "sess-1"

# ── 请求构造 ──


def test_build_headers_contains_api_key_and_resource_id():
    headers = build_headers("test-api-key")
    assert headers["X-Api-Key"] == "test-api-key"
    assert headers["X-Api-Resource-Id"] == "seed-tts-2.0"
    assert headers["X-Control-Require-Usage-Tokens-Return"] == "*"
    # 每次请求生成唯一 uuid
    assert build_headers("k")["X-Api-Request-Id"] != headers["X-Api-Request-Id"]


def test_build_request_payload_defaults():
    payload = build_request_payload("你好直播间的朋友们")
    params = payload["req_params"]
    assert params["text"] == "你好直播间的朋友们"
    assert params["speaker"] == "zh_female_vv_uranus_bigtts"
    assert params["audio_params"]["format"] == "pcm"
    assert params["audio_params"]["sample_rate"] == 24000


def test_build_request_payload_custom_speaker_and_rate():
    payload = build_request_payload("hi", speaker="zh_male_x", sample_rate=16000)
    params = payload["req_params"]
    assert params["speaker"] == "zh_male_x"
    assert params["audio_params"]["sample_rate"] == 16000


# ── 二进制帧编解码 ──


def test_encode_full_client_request_roundtrip():
    payload = json.dumps({"req_params": {"text": "hi"}}).encode()
    data = encode_full_client_request(payload)
    assert data[:3] == b"\x11\x10\x10"  # version1/hdr4, full-request/noseq, json/none
    size = struct.unpack(">I", data[4:8])[0]
    assert size == len(payload)
    frame = decode_frame(data)
    assert frame.msg_type == MSG_FULL_CLIENT_REQUEST
    assert frame.payload == payload


def test_decode_audio_frame_with_event():
    audio = b"\x00\x01fake-pcm"
    data = encode_frame(
        MSG_AUDIO_ONLY_SERVER, audio, flag=FLAG_WITH_EVENT,
        event=EVENT_TTS_RESPONSE, session_id=SESSION,
    )
    frame = decode_frame(data)
    assert frame.msg_type == MSG_AUDIO_ONLY_SERVER
    assert frame.event == EVENT_TTS_RESPONSE
    assert frame.session_id == SESSION
    assert frame.payload == audio


def test_decode_session_finished_frame():
    data = encode_frame(
        MSG_FULL_SERVER_RESPONSE, b"{}", flag=FLAG_WITH_EVENT,
        event=EVENT_SESSION_FINISHED, session_id=SESSION,
    )
    frame = decode_frame(data)
    assert frame.event == EVENT_SESSION_FINISHED
    assert frame.payload == b"{}"


def test_decode_error_frame_carries_code_and_message():
    data = encode_frame(MSG_ERROR, b'{"error":"boom"}', error_code=45000001)
    frame = decode_frame(data)
    assert frame.msg_type == MSG_ERROR
    assert frame.error_code == 45000001
    assert frame.payload == b'{"error":"boom"}'


def test_decode_gzip_compressed_payload():
    import gzip

    audio = b"\x11\x22compressed"
    data = encode_frame(MSG_AUDIO_ONLY_SERVER, gzip.compress(audio), flag=FLAG_WITH_EVENT,
                        event=EVENT_TTS_RESPONSE, session_id=SESSION)
    # 手动把压缩标志位改为 gzip（encode_frame 固定输出 none）
    patched = bytearray(data)
    patched[2] = (1 << 4) | 0x1
    frame = decode_frame(bytes(patched))
    assert frame.payload == audio


def test_decode_frame_too_short_raises():
    with pytest.raises(ValueError):
        decode_frame(b"\x11")


# ── speak 全流程（fake 连接 + fake 播放器）──


class FakePlayer:
    """替代 sounddevice 播放器：记录写入的音频块。"""

    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.drained = False
        self.closed = False

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    def drain(self) -> None:
        self.drained = True

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    """替代 websockets 连接：发送一次请求，回放预设帧序列（bytes 二进制帧）。"""

    def __init__(self, frames: list[bytes]) -> None:
        self.frames = frames
        self.sent: list[bytes] = []
        self.closed = False

    async def send(self, message: bytes) -> None:
        self.sent.append(message)

    async def recv(self) -> bytes:
        if not self.frames:
            raise AssertionError("recv called more times than frames provided")
        return self.frames.pop(0)

    async def close(self) -> None:
        self.closed = True


def make_settings(api_key: str = "test-key"):
    class S:
        tts_cloud_api_key = api_key
        tts_cloud_speaker = "zh_female_vv_uranus_bigtts"

    return S()


async def _fake_connect(conn: FakeConnection):
    return conn


def audio_frame(audio: bytes) -> bytes:
    return encode_frame(MSG_AUDIO_ONLY_SERVER, audio, flag=FLAG_WITH_EVENT,
                        event=EVENT_TTS_RESPONSE, session_id=SESSION)


async def test_speak_streams_audio_chunks_to_player():
    raw1, raw2 = b"chunk-one", b"chunk-two"
    frames = [
        encode_frame(MSG_FULL_SERVER_RESPONSE, b'{"text":"x"}', flag=FLAG_WITH_EVENT,
                     event=350, session_id=SESSION),  # TTSSentenceStart
        audio_frame(raw1),
        audio_frame(raw2),
        encode_frame(MSG_FULL_SERVER_RESPONSE, b"{}", flag=FLAG_WITH_EVENT,
                     event=EVENT_SESSION_FINISHED, session_id=SESSION),
    ]
    conn = FakeConnection(frames)
    player = FakePlayer()
    tts = CloudTTS(make_settings(), connect_factory=lambda: _fake_connect(conn), player=player)

    await tts.speak("测试播报")

    # 请求为 FullClientRequest 二进制帧，JSON 里带文本
    assert len(conn.sent) == 1
    request = decode_frame(conn.sent[0])
    assert request.msg_type == MSG_FULL_CLIENT_REQUEST
    params = json.loads(request.payload)["req_params"]
    assert params["text"] == "测试播报"
    # 音频块顺序写入播放器，最后排空
    assert player.chunks == [raw1, raw2]
    assert player.drained
    assert conn.closed


async def test_speak_skips_when_key_missing(caplog):
    player = FakePlayer()
    tts = CloudTTS(
        make_settings(api_key=""),
        connect_factory=lambda: _fake_connect(FakeConnection([])),
        player=player,
    )
    with caplog.at_level("ERROR"):
        await tts.speak("不应播报")
    assert player.chunks == []
    assert "密钥" in caplog.text


async def test_speak_survives_connection_error(caplog):
    """连接失败只记日志，不抛出中断播报循环。"""
    player = FakePlayer()

    async def broken_connect():
        raise OSError("network down")

    tts = CloudTTS(make_settings(), connect_factory=broken_connect, player=player)
    with caplog.at_level("ERROR"):
        await tts.speak("网络故障")
    assert player.chunks == []
    assert "网络" in caplog.text or "失败" in caplog.text


async def test_speak_survives_server_error_frame():
    """服务端返回 Error 帧（如配额超限）时跳过播报、不抛异常。"""
    frames = [encode_frame(MSG_ERROR, b'{"error":"quota"}', error_code=45000001)]
    conn = FakeConnection(frames)
    player = FakePlayer()
    tts = CloudTTS(make_settings(), connect_factory=lambda: _fake_connect(conn), player=player)
    await tts.speak("配额超限")
    assert player.chunks == []
    assert conn.closed


async def test_speak_survives_session_failed_event():
    frames = [
        encode_frame(MSG_FULL_SERVER_RESPONSE, b'{"message":"failed"}',
                     flag=FLAG_WITH_EVENT, event=EVENT_SESSION_FAILED, session_id=SESSION),
    ]
    conn = FakeConnection(frames)
    player = FakePlayer()
    tts = CloudTTS(make_settings(), connect_factory=lambda: _fake_connect(conn), player=player)
    await tts.speak("会话失败")
    assert player.chunks == []
    assert conn.closed


async def test_speak_reports_usage_to_charge_hook():
    """实测：计费字数随 SessionFinished 负载返回 {"usage":{"text_words":N}}。"""
    reported: list[dict] = []
    frames = [
        audio_frame(b"a"),
        encode_frame(MSG_FULL_SERVER_RESPONSE, b'{"usage":{"text_words": 6}}',
                     flag=FLAG_WITH_EVENT, event=EVENT_SESSION_FINISHED, session_id=SESSION),
    ]
    conn = FakeConnection(frames)
    tts = CloudTTS(
        make_settings(),
        connect_factory=lambda: _fake_connect(conn),
        player=FakePlayer(),
        charge_hook=reported.append,
    )
    await tts.speak("计费")
    assert reported == [{"text_words": 6}]


async def test_speak_reports_usage_response_event_to_charge_hook():
    """UsageResponse(154) 独立事件兜底（协议预留路径）。"""
    reported: list[dict] = []
    frames = [
        encode_frame(MSG_FULL_SERVER_RESPONSE, b'{"text_words": 5}',
                     flag=FLAG_WITH_EVENT, event=EVENT_USAGE_RESPONSE, session_id=SESSION),
        encode_frame(MSG_FULL_SERVER_RESPONSE, b"{}", flag=FLAG_WITH_EVENT,
                     event=EVENT_SESSION_FINISHED, session_id=SESSION),
    ]
    conn = FakeConnection(frames)
    tts = CloudTTS(
        make_settings(),
        connect_factory=lambda: _fake_connect(conn),
        player=FakePlayer(),
        charge_hook=reported.append,
    )
    await tts.speak("计费")
    assert reported == [{"text_words": 5}]


# ── 事件循环不阻塞 + 资源回收（2026-09-19 现场调试）──


async def test_speak_does_not_block_event_loop():
    """player.write 阻塞时事件循环必须仍能调度其他协程。

    现场：write/drain 阻塞调用直接跑在事件循环里，播报期间收弹幕/
    心跳全部冻结，websockets keepalive 20s 收不到 pong 即杀连接。
    """
    import asyncio
    import time

    class SlowPlayer(FakePlayer):
        def write(self, data: bytes) -> None:
            time.sleep(0.3)  # 模拟 sounddevice 阻塞写入
            super().write(data)

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    frames = [
        audio_frame(b"a"),
        encode_frame(MSG_FULL_SERVER_RESPONSE, b"{}", flag=FLAG_WITH_EVENT,
                     event=EVENT_SESSION_FINISHED, session_id=SESSION),
    ]
    conn = FakeConnection(frames)
    tts = CloudTTS(make_settings(), connect_factory=lambda: _fake_connect(conn),
                   player=SlowPlayer())
    task = asyncio.create_task(ticker())
    await asyncio.sleep(0.05)
    before = ticks
    await tts.speak("不应阻塞循环")
    after = ticks
    task.cancel()
    assert after - before > 5, f"事件循环被阻塞（tick 仅 {after - before} 次）"


async def test_speak_closes_player():
    """每次播报后必须关闭音频流（原实现泄漏 PortAudio 流）。"""
    frames = [
        audio_frame(b"a"),
        encode_frame(MSG_FULL_SERVER_RESPONSE, b"{}", flag=FLAG_WITH_EVENT,
                     event=EVENT_SESSION_FINISHED, session_id=SESSION),
    ]
    conn = FakeConnection(frames)
    player = FakePlayer()
    tts = CloudTTS(make_settings(), connect_factory=lambda: _fake_connect(conn), player=player)
    await tts.speak("资源回收")
    assert player.closed
