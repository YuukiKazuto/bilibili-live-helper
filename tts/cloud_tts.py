"""云端 TTS：火山引擎豆包语音（单向流式 WebSocket，二进制帧协议）。

接入规范（.claude/rules/06-volcengine-tts.md）：
- 端点 wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream
- 新版控制台鉴权：X-Api-Key + X-Api-Resource-Id(seed-tts-2.0) + X-Api-Request-Id(uuid)
- 请求为 FullClientRequest 二进制帧包 JSON（协议见 tts/volcengine_proto.py）；
  响应流式返回 PCM 音频帧，边收边播，读完排空（保证队列顺序播报）
- 密钥只从项目配置文件读取（Settings），缺失明确提示；失败记日志跳过，不中断播报循环
- 计费钩子预留（阶段 2 订阅制）：UsageResponse 事件 / usage 字数
"""
import json
import logging
import uuid
from typing import Any, Awaitable, Callable

import sounddevice as sd
import websockets

from tts.base import TTSProvider
from tts.volcengine_proto import (
    EVENT_SESSION_FAILED,
    EVENT_SESSION_FINISHED,
    EVENT_USAGE_RESPONSE,
    FLAG_WITH_EVENT,
    Frame,
    MSG_AUDIO_ONLY_SERVER,
    MSG_ERROR,
    decode_frame,
    encode_full_client_request,
)

logger = logging.getLogger(__name__)

# 协议常量（见 rules/06）
WSS_ENDPOINT = "wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream"
RESOURCE_ID = "seed-tts-2.0"
SAMPLE_RATE = 24000
DEFAULT_SPEAKER = "zh_female_vv_uranus_bigtts"
CHANNELS = 1

ConnectFactory = Callable[[], Awaitable[Any]]


def build_headers(api_key: str) -> dict[str, str]:
    """构造鉴权与请求标识请求头。"""
    return {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Request-Id": str(uuid.uuid4()),
        # 要求服务端返回本次计费字符数（UsageResponse 事件）
        "X-Control-Require-Usage-Tokens-Return": "*",
    }


def build_request_payload(
    text: str,
    speaker: str = DEFAULT_SPEAKER,
    sample_rate: int = SAMPLE_RATE,
) -> dict:
    """构造合成请求 JSON：一次性文本输入，流式 PCM 输出。"""
    return {
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {
                "format": "pcm",
                "sample_rate": sample_rate,
            },
        }
    }


class PcmPlayer:
    """sounddevice PCM 播放器：write() 边收边播，drain() 等待播放排空。"""

    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        self._stream = sd.RawOutputStream(
            samplerate=sample_rate,
            channels=CHANNELS,
            dtype="int16",
        )
        self._stream.start()

    def write(self, data: bytes) -> None:
        self._stream.write(data)

    def drain(self) -> None:
        self._stream.stop()  # 播完缓冲区剩余音频后才返回

    def close(self) -> None:
        self._stream.close()


class CloudTTS(TTSProvider):
    """火山引擎云端 TTS 实现。"""

    def __init__(
        self,
        settings,
        *,
        connect_factory: ConnectFactory | None = None,
        player: Any = None,
        charge_hook: Callable[[dict], None] | None = None,
    ) -> None:
        """connect_factory/player 可注入以便测试；生产环境用默认值。"""
        self.settings = settings
        self.speaker = getattr(settings, "tts_cloud_speaker", "") or DEFAULT_SPEAKER
        self._connect_factory = connect_factory or self._default_connect
        self._player_factory = (lambda: player) if player is not None else PcmPlayer
        # 订阅制计费钩子（阶段 2 预留：订阅态校验、用量上报）
        self._charge_hook = charge_hook or self._charge_hook
        if not settings.tts_cloud_api_key:
            # 明确提示密钥缺失（UI 层据此展示配置引导）
            logger.warning("云端 TTS 密钥未配置，请在项目配置文件中填写 TTS_CLOUD_API_KEY")

    async def speak(self, text: str) -> None:
        if not self.settings.tts_cloud_api_key:
            logger.error("[云端TTS] 密钥缺失，跳过播报: %s", text)
            return
        conn = None
        try:
            player = self._player_factory()
            conn = await self._connect_factory()
            request = json.dumps(build_request_payload(text, speaker=self.speaker))
            await conn.send(encode_full_client_request(request.encode("utf-8")))

            usage = None
            while True:
                frame: Frame = decode_frame(await conn.recv())
                if frame.msg_type == MSG_AUDIO_ONLY_SERVER:
                    player.write(frame.payload)
                elif frame.msg_type == MSG_ERROR:
                    logger.error(
                        "[云端TTS] 合成失败 code=%s: %s",
                        frame.error_code,
                        frame.payload.decode("utf-8", "ignore"),
                    )
                    break
                elif frame.flag == FLAG_WITH_EVENT and frame.event == EVENT_USAGE_RESPONSE:
                    try:
                        usage = json.loads(frame.payload)
                    except json.JSONDecodeError:
                        logger.warning("[云端TTS] 用量帧解析失败: %r", frame.payload)
                elif frame.flag == FLAG_WITH_EVENT and frame.event == EVENT_SESSION_FINISHED:
                    # 计费字数随 SessionFinished 负载返回（实测：{"usage":{"text_words":N}}）
                    try:
                        usage = json.loads(frame.payload).get("usage") or usage
                    except json.JSONDecodeError:
                        pass
                    break
                elif frame.flag == FLAG_WITH_EVENT and frame.event == EVENT_SESSION_FAILED:
                    logger.error("[云端TTS] 会话失败: %r", frame.payload)
                    break

            player.drain()
            if usage:
                self._charge_hook(usage)
        except Exception:
            logger.exception("[云端TTS] 播报失败，跳过: %s", text)
        finally:
            if conn is not None:
                await conn.close()

    async def _default_connect(self):
        """生产连接：每次合成建立一条 WebSocket（无状态，失败即弃）。"""
        return await websockets.connect(
            WSS_ENDPOINT,
            additional_headers=build_headers(self.settings.tts_cloud_api_key),
            max_size=10 * 1024 * 1024,
        )

    async def _charge_hook(self, usage: dict) -> None:
        """订阅制计费钩子（阶段 2 预留：订阅态校验、用量上报）。"""

    async def close(self) -> None:
        pass
