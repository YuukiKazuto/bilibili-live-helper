"""服务接口的进程内实现（阶段 1）。

后台线程运行 asyncio 事件循环，组装 核心链路：
弹幕源 → 事件总线 →（播报策略 → 播报队列 → TTS + 前端事件订阅者）。

start() 非阻塞；stop() 线程安全地请求停止并等待资源释放。
每次 start() 重新构建 TTS/队列/播报策略（偏好改动生效）。
"""
import asyncio
import logging
import threading
from contextlib import suppress

from config.loader import Settings, load_settings
from config.preferences import Preferences, PreferenceStore
from core.broadcast_queue import BroadcastQueue
from core.broadcaster import Broadcaster
from core.event_bus import EventBus
from platforms.bilibili.client import BilibiliLiveClient
from service.base import (
    EventCallback,
    LiveHelperService,
    ModelInfo,
    ProgressCallback,
    ServiceError,
)
from tts.base import TTSProvider
from tts.cloud_tts import CloudTTS
from tts.local.model_manager import (
    AVAILABLE_MODELS,
    ModelManager,
    find_model,
    resolve_models_dir,
)
from tts.local_tts import LocalTTS

logger = logging.getLogger(__name__)


def _build_tts(settings: Settings, prefs: Preferences) -> TTSProvider:
    """按偏好构建 TTS（本地/云端可插拔）。"""
    if prefs.tts_mode == "cloud":
        return CloudTTS(settings)
    return LocalTTS(
        settings,
        prefs.tts_local_model,
        models_dir=resolve_models_dir(prefs.models_dir),
    )


class LocalLiveService(LiveHelperService):
    """进程内服务实现：单后台线程 + asyncio 事件循环。"""

    def __init__(
        self,
        settings: Settings | None = None,
        prefs: Preferences | None = None,
        platform_factory=None,
    ) -> None:
        """platform_factory 可注入测试替身；生产默认 B站客户端。"""
        self.settings = settings or load_settings()
        self.prefs = prefs or PreferenceStore.load()
        self._platform_factory = platform_factory or (
            lambda s, id_code, on_event: BilibiliLiveClient(
                settings=s, id_code=id_code, on_event=on_event
            )
        )
        self._manager = ModelManager(resolve_models_dir(self.prefs.models_dir))

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = threading.Event()
        # 停止信号：threading.Event 保证 stop() 在循环未就绪时调用也有效
        self._stop_requested = threading.Event()
        self._event_cbs: list[EventCallback] = []
        self._cbs_lock = threading.Lock()

    # ── 偏好配置 ──

    def get_preferences(self) -> Preferences:
        return self.prefs

    def save_preferences(self) -> None:
        PreferenceStore.save(self.prefs)

    def warnings(self) -> list[str]:
        out = self.settings.validate()
        if self.prefs.tts_mode == "cloud" and not self.settings.tts_cloud_api_key:
            out.append("云端 TTS 密钥未配置，请在配置文件中填写 TTS_CLOUD_API_KEY")
        return out

    # ── 生命周期 ──

    def start(self) -> None:
        if self._running.is_set():
            raise ServiceError("服务已在运行中")
        if not self.prefs.bili_id_code:
            raise ServiceError("请先在设置中填写主播身份码")

        self._stop_requested.clear()
        self._thread = threading.Thread(
            target=self._thread_main, name="live-service", daemon=True
        )
        self._running.set()
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        if not self._running.is_set():
            return
        # threading.Event 跨线程立即生效，无需等待事件循环就绪
        self._stop_requested.set()
        if self._thread is not None:
            self._thread.join(timeout)
        if self._running.is_set():
            logger.warning("[服务] stop 超时，后台线程未在 %.1fs 内退出", timeout)

    def is_running(self) -> bool:
        return self._running.is_set()

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception:  # noqa: BLE001 — 后台线程异常必须落日志
            logger.exception("[服务] 事件循环异常退出")
        finally:
            self._running.clear()

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()

        # 组装核心链路（每次 start 重建，使偏好改动生效）
        bus = EventBus()
        tts = _build_tts(self.settings, self.prefs)
        queue = BroadcastQueue(tts.speak)
        queue.start()
        broadcaster = Broadcaster(self.prefs, queue)
        bus.subscribe(broadcaster.on_event)
        bus.subscribe(self._dispatch)  # 前端事件订阅者（互动面板展示）

        platform = self._platform_factory(
            self.settings, self.prefs.bili_id_code, bus.publish
        )
        platform_task = asyncio.create_task(self._platform_run(platform))
        # 停止信号等待（to_thread 中 wait，set 后立即返回）
        stop_task = asyncio.create_task(
            asyncio.to_thread(self._stop_requested.wait)
        )
        try:
            # 平台自行退出（断线）或收到停止请求，二者任一结束服务
            await asyncio.wait(
                {platform_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            # 先置位停止信号：解除 to_thread 等待线程（stop_task），
            # 否则平台自行退出（没点停止）时 asyncio.run 关闭默认线程池会永久挂起
            self._stop_requested.set()
            stop_task.cancel()
            platform_task.cancel()
            try:
                await platform_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                # 平台以真实异常退出（断线 / keepalive 超时等）视为正常收尾，
                # 只记日志，不向上抛（现场：ConnectionClosedError 穿透导致
                # 「[服务] 事件循环异常退出」堆栈，即用户看到的「停止异常」）
                logger.info("[服务] 平台连接退出: %s", exc)
            with suppress(Exception):
                await platform.close()
            await queue.stop()
            await tts.close()
            logger.info("[服务] 已停止")

    async def _platform_run(self, platform) -> None:
        await platform.connect()
        await platform.run()

    # ── 事件流 ──

    def subscribe_events(self, callback: EventCallback) -> None:
        with self._cbs_lock:
            if callback not in self._event_cbs:
                self._event_cbs.append(callback)

    def unsubscribe_events(self, callback: EventCallback) -> None:
        with self._cbs_lock:
            if callback in self._event_cbs:
                self._event_cbs.remove(callback)

    def _dispatch(self, event) -> None:
        """把统一事件分发给前端订阅者（在服务线程中同步调用）。"""
        with self._cbs_lock:
            callbacks = list(self._event_cbs)
        for cb in callbacks:
            try:
                cb(event)
            except Exception:  # noqa: BLE001 — 单个订阅者异常不影响其他
                logger.exception("[服务] 事件订阅者处理异常: %r", event)

    # ── 本地 TTS 模型管理 ──

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                model_id=m.model_id,
                display_name=m.display_name,
                license=m.license,
                size_hint=m.size_hint,
                downloaded=self._manager.is_downloaded(m),
            )
            for m in AVAILABLE_MODELS
        ]

    async def download_model(self, model_id: str, progress: ProgressCallback | None = None) -> None:
        model = find_model(model_id)
        if model is None:
            raise ServiceError(f"未知模型: {model_id}")
        await asyncio.to_thread(self._manager.download, model, progress)
