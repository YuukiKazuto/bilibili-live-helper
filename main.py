"""B站直播弹幕播报辅助工具 — 程序入口（阶段 1 桌面 App）。

启动流程：加载配置 → 初始化事件总线/播报队列/播报策略/TTS → 连接弹幕源。
"""
import asyncio

from config.loader import load_settings
from config.preferences import PreferenceStore
from core.event_bus import EventBus
from core.broadcast_queue import BroadcastQueue
from core.broadcaster import Broadcaster
from tts.local_tts import LocalTTS
from tts.cloud_tts import CloudTTS
from platforms.bilibili.client import BilibiliLiveClient
from utils.logging_setup import setup_logging


async def run() -> None:
    setup_logging()

    # 1. 密钥/常驻配置（.env / config.json）
    settings = load_settings()

    # 2. 用户偏好（开关、阈值、身份码等，本地持久化）
    prefs = PreferenceStore.load()

    # 3. 组装核心链路：事件总线 → 播报策略 → 播报队列 → TTS
    bus = EventBus()
    tts = CloudTTS(settings) if prefs.tts_mode == "cloud" else LocalTTS(settings, prefs.tts_local_model)
    queue = BroadcastQueue(tts.speak)
    queue.start()  # 单工作协程：顺序播报，付费事件插队但不打断
    broadcaster = Broadcaster(prefs, queue)
    bus.subscribe(broadcaster.on_event)

    # 4. 连接弹幕源（阶段 1 仅 B站；身份码来自 UI 保存的偏好）
    platform = BilibiliLiveClient(
        settings=settings,
        id_code=prefs.bili_id_code,
        on_event=bus.publish,
    )
    try:
        await platform.connect()
        await platform.run()
    finally:
        await platform.close()
        await queue.stop()
        await tts.close()


if __name__ == "__main__":
    asyncio.run(run())
