"""B站开放平台弹幕源客户端（参考官方 demo/ws.py，工程化整理）。

流程：
1. POST /v2/app/start（身份码 + app_id）→ 拿 wss 地址与 auth_body
2. WebSocket 连接 → 发送鉴权包（op=7）
3. 并行：收消息循环 + 连接心跳（op=2，20s）+ 应用心跳（/v2/app/heartbeat，20s）
4. 退出时 POST /v2/app/end 结束应用会话

密钥来自项目配置文件；主播身份码来自用户偏好（UI 填写并本地保存）。
"""
import asyncio
import hashlib
import hmac
import json
import logging
import random
import time
from hashlib import sha256

import aiohttp
import websockets

from config.loader import Settings
from platforms.base import LiveEvent, PlatformBase
from platforms.bilibili.proto import Proto, OP_AUTH, OP_HEARTBEAT, OP_MESSAGE
from platforms.bilibili.events import parse_command

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 20  # 秒


class BilibiliLiveClient(PlatformBase):
    """B站直播间长连客户端。"""

    def __init__(self, settings: Settings, id_code: str, on_event) -> None:
        super().__init__(on_event)
        self.settings = settings
        self.id_code = id_code
        self.game_id = ""
        self._ws = None
        self._session: aiohttp.ClientSession | None = None

    # ── HTTP 签名（x-bili-* 头按字典序拼接后 HMAC-SHA256）──

    def _sign(self, params: str) -> dict:
        md5 = hashlib.md5(params.encode()).hexdigest()
        ts = int(time.time())
        nonce = str(random.randint(1, 100000) + int(time.time() * 1000))
        header_map = {
            "x-bili-timestamp": str(ts),
            "x-bili-signature-method": "HMAC-SHA256",
            "x-bili-signature-nonce": nonce,
            "x-bili-accesskeyid": self.settings.bili_access_key,
            "x-bili-signature-version": "1.0",
            "x-bili-content-md5": md5,
        }
        header_str = "\n".join(f"{k}:{v}" for k, v in sorted(header_map.items()))
        signature = hmac.new(
            self.settings.bili_access_secret.encode(), header_str.encode(), digestmod=sha256
        ).hexdigest()
        header_map["Authorization"] = signature
        header_map["Content-Type"] = "application/json"
        header_map["Accept"] = "application/json"
        return header_map

    async def _post(self, path: str, params: dict) -> dict:
        url = f"{self.settings.bili_api_host}{path}"
        body = json.dumps(params)
        headers = self._sign(body)
        async with self._session.post(url, headers=headers, data=body) as resp:
            data = await resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"B站接口错误 {path}: {data}")
        return data["data"]

    # ── 生命周期 ──

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession()
        # 开启应用：换取 wss 地址与鉴权体
        data = await self._post("/v2/app/start", {
            "code": self.id_code,
            "app_id": self.settings.bili_app_id,
        })
        self.game_id = data["game_info"]["game_id"]
        wss_link = data["websocket_info"]["wss_link"][0]
        auth_body = data["websocket_info"]["auth_body"]

        logger.info("应用已启动 game_id=%s，建立长连...", self.game_id)
        self._ws = await websockets.connect(wss_link)
        await self._auth(auth_body)

    async def _auth(self, auth_body: str) -> None:
        req = Proto()
        req.body = auth_body.encode()
        req.op = OP_AUTH
        await self._ws.send(req.pack())
        buf = await self._ws.recv()
        for frame in Proto.frames(buf):
            if frame.op == 8 and json.loads(frame.body)["code"] != 0:
                raise RuntimeError("B站长连鉴权失败")

    async def run(self) -> None:
        """并行：收消息 + 连接心跳 + 应用心跳。"""
        tasks = [
            asyncio.create_task(self._recv_loop()),
            asyncio.create_task(self._ws_heartbeat_loop()),
            asyncio.create_task(self._app_heartbeat_loop()),
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                t.cancel()

    async def close(self) -> None:
        # 结束应用会话
        if self.game_id and self._session:
            try:
                await self._post("/v2/app/end", {
                    "game_id": self.game_id,
                    "app_id": self.settings.bili_app_id,
                })
            except Exception:  # noqa: BLE001
                logger.exception("结束应用会话失败")
        if self._ws:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001 — 关闭握手超时等（现场实测 TimeoutError）不影响收尾
                logger.warning("关闭长连异常（忽略）: %s", self._ws)
        if self._session:
            await self._session.close()

    # ── 循环 ──

    async def _recv_loop(self) -> None:
        async for buf in self._ws:
            for frame in Proto.frames(buf):
                if frame.op != OP_MESSAGE or not frame.body:
                    continue
                try:
                    cmd_data = json.loads(frame.body)
                except json.JSONDecodeError:
                    logger.warning("消息体非 JSON: %r", frame.body[:100])
                    continue
                for event in parse_command(cmd_data):
                    await self.on_event(event)

    async def _ws_heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            req = Proto()
            req.op = OP_HEARTBEAT
            await self._ws.send(req.pack())

    async def _app_heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            await self._post("/v2/app/heartbeat", {"game_id": self.game_id})
            logger.debug("应用心跳成功")
