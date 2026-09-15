"""B站长连二进制协议打包/解包（参考官方 demo/proto.py，工程化整理）。

包结构（大端）：packetLen(4) | headerLen(2) | ver(2) | op(4) | seq(4) | body
"""
import struct

HEADER_LEN = 16
OP_HEARTBEAT = 2          # 心跳请求
OP_HEARTBEAT_REPLY = 3    # 心跳回复（人气值）
OP_MESSAGE = 5            # 普通消息（命令）
OP_AUTH = 7               # 鉴权请求
OP_AUTH_REPLY = 8         # 鉴权回复


class Proto:
    """一帧的打包与解包。"""

    def __init__(self) -> None:
        self.packet_len = 0
        self.ver = 0
        self.op = 0
        self.seq = 1
        self.body = b""

    def pack(self) -> bytes:
        """按协议打包为一帧二进制数据。"""
        self.packet_len = len(self.body) + HEADER_LEN
        return (
            struct.pack(">i", self.packet_len)
            + struct.pack(">h", HEADER_LEN)
            + struct.pack(">h", self.ver)
            + struct.pack(">i", self.op)
            + struct.pack(">i", self.seq)
            + self.body
        )

    def unpack(self, buf: bytes) -> "Proto | None":
        """解包单帧；返回自身，包不完整/非法时返回 None。"""
        if len(buf) < HEADER_LEN:
            return None
        self.packet_len = struct.unpack(">i", buf[0:4])[0]
        self.op = struct.unpack(">i", buf[8:12])[0]
        self.seq = struct.unpack(">i", buf[12:16])[0]
        if self.packet_len < HEADER_LEN or self.packet_len > len(buf):
            return None
        self.body = buf[HEADER_LEN:self.packet_len]
        return self

    @staticmethod
    def frames(buf: bytes) -> list["Proto"]:
        """一次 recv 可能含多帧，循环切分。"""
        out = []
        offset = 0
        while offset + HEADER_LEN <= len(buf):
            p = Proto()
            if p.unpack(buf[offset:]) is None:
                break
            out.append(p)
            offset += p.packet_len
        return out
