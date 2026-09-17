"""火山引擎豆包语音 WebSocket 二进制协议（单向流式，V3）。

帧格式以官方 demo（websocket unidirectional/protocols.py）为准：

    0                 1                 2                 3
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    | Version(4b) | HeaderSize(4b) | MsgType(4b) | Flags(4b) |
    | Serialization(4b) | Compression(4b) | Reserved(8b)    |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    | 可选附加字段（按 msg_type/flags 依次出现）             |
    | 4B 负载长度 + 负载                                     |

单向流式 TTS 用法：
- 客户端发一帧 FullClientRequest（flag=NoSeq），payload 为 JSON（req_params）。
- 服务端回二进制帧：AudioOnlyServer 携带裸音频块，FullServerResponse 携带事件
  （TTSSentenceStart=350 / TTSSentenceEnd=351 / TTSResponse=352 / SessionFinished=152 /
  SessionFailed=153 / UsageResponse=154），Error 帧携带错误码与 JSON 错误信息。

接入规范见 .claude/rules/06-volcengine-tts.md。
"""
import gzip
import struct
from dataclasses import dataclass

# 消息类型（byte1 高 4 位）
MSG_FULL_CLIENT_REQUEST = 0x1
MSG_FULL_SERVER_RESPONSE = 0x9
MSG_AUDIO_ONLY_SERVER = 0xB
MSG_ERROR = 0xF

# 标志位（byte1 低 4 位）
FLAG_NO_SEQ = 0x0      # 无序列号
FLAG_POS_SEQ = 0x1     # 非末包，带正序列号
FLAG_LAST_NO_SEQ = 0x2 # 末包，无序列号
FLAG_NEG_SEQ = 0x3     # 末包，带负序列号
FLAG_WITH_EVENT = 0x4  # 负载前带事件号（int32）

# 事件号（FLAG_WITH_EVENT 帧的负载前置 int32）
EVENT_SESSION_FINISHED = 152
EVENT_SESSION_FAILED = 153
EVENT_USAGE_RESPONSE = 154  # 计费用量（配合请求头 X-Control-Require-Usage-Tokens-Return）
EVENT_TTS_SENTENCE_START = 350
EVENT_TTS_SENTENCE_END = 351
EVENT_TTS_RESPONSE = 352

# 带序列号附加字段的消息类型
_SEQ_TYPES = {MSG_FULL_CLIENT_REQUEST, MSG_FULL_SERVER_RESPONSE, MSG_AUDIO_ONLY_SERVER}
# 连接级事件（无 session_id / connect_id 附加字段的例外，见官方 demo）
_CONNECTION_EVENTS = {1, 2, 50, 51, 52}


@dataclass(frozen=True)
class Frame:
    """解码后的一帧消息。"""

    msg_type: int
    flag: int = FLAG_NO_SEQ
    event: int = 0
    session_id: str = ""
    sequence: int = 0
    error_code: int = 0
    payload: bytes = b""


def encode_frame(
    msg_type: int,
    payload: bytes,
    flag: int = FLAG_NO_SEQ,
    event: int = 0,
    session_id: str = "",
    sequence: int = 0,
    error_code: int = 0,
) -> bytes:
    """按官方帧格式编码（header_size=4，JSON 序列化，无压缩）。"""
    out = bytearray()
    out.append((1 << 4) | 1)  # version=1, header_size=1（4 字节）
    out.append((msg_type << 4) | flag)
    out.append((1 << 4) | 0)  # serialization=JSON, compression=none
    out.append(0)             # reserved

    if flag == FLAG_WITH_EVENT:
        out += struct.pack(">i", event)
        if event not in _CONNECTION_EVENTS:
            sid = session_id.encode("utf-8")
            out += struct.pack(">I", len(sid)) + sid
    if msg_type in _SEQ_TYPES and flag in (FLAG_POS_SEQ, FLAG_NEG_SEQ):
        out += struct.pack(">i", sequence)
    if msg_type == MSG_ERROR:
        out += struct.pack(">I", error_code)

    out += struct.pack(">I", len(payload)) + payload
    return bytes(out)


def encode_full_client_request(payload: bytes) -> bytes:
    """客户端合成请求帧：JSON 负载（req_params），无事件号。"""
    return encode_frame(MSG_FULL_CLIENT_REQUEST, payload)


def decode_frame(data: bytes) -> Frame:
    """解码一帧二进制消息（字段顺序见模块 docstring / 官方 demo）。"""
    if len(data) < 4:
        raise ValueError(f"帧过短: {len(data)}B")
    version_and_hdr = data[0]
    header_size = 4 * (version_and_hdr & 0x0F)
    msg_type = data[1] >> 4
    flag = data[1] & 0x0F
    compression = data[2] & 0x0F
    pos = header_size

    sequence = 0
    if msg_type in _SEQ_TYPES and flag in (FLAG_POS_SEQ, FLAG_NEG_SEQ):
        sequence = struct.unpack(">i", data[pos:pos + 4])[0]
        pos += 4

    error_code = 0
    if msg_type == MSG_ERROR:
        error_code = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4

    event, session_id = 0, ""
    if flag == FLAG_WITH_EVENT:
        event = struct.unpack(">i", data[pos:pos + 4])[0]
        pos += 4
        if event not in _CONNECTION_EVENTS:
            sid_size = struct.unpack(">I", data[pos:pos + 4])[0]
            pos += 4
            session_id = data[pos:pos + sid_size].decode("utf-8")
            pos += sid_size

    payload_size = struct.unpack(">I", data[pos:pos + 4])[0]
    pos += 4
    payload = data[pos:pos + payload_size]
    if compression == 0x1:
        payload = gzip.decompress(payload)

    return Frame(
        msg_type=msg_type,
        flag=flag,
        event=event,
        session_id=session_id,
        sequence=sequence,
        error_code=error_code,
        payload=payload,
    )
