"""前端服务接口定义（抽象基类）。

阶段 1 由 service/local.py 进程内实现；阶段 2 由 HTTP/WebSocket 客户端实现
同一接口，前端代码零改动（.claude/rules/01-architecture.md「两阶段架构」）。

约定：
- 除标注 async 的方法外均为同步调用，UI 线程可直接调用。
- 事件回调在服务线程/远程推送线程中触发，前端自行跨线程投递到 UI 线程
  （如 Qt 信号槽，见 rules/07「跨线程投递」）。
- get_preferences() 返回服务持有的同一 Preferences 对象：UI 修改字段后调
  save_preferences() 持久化；开关/阈值改动即时生效（同一引用），
  TTS 模式等构建期配置在下次 start() 时生效。
"""
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

from config.preferences import Preferences

# 事件回调：收到统一事件（platforms.base.LiveEvent）时触发（同步调用）
EventCallback = Callable[[object], None]
# 模型下载进度回调：已完成字节数, 总字节数（None 表示未知）
ProgressCallback = Callable[[int, int | None], None]


class ServiceError(Exception):
    """服务层业务错误（如身份码未填写、未知模型），前端可直接展示 message。"""


@dataclass(frozen=True)
class ModelInfo:
    """本地 TTS 模型摘要（前端展示用，不含路径/下载源等实现细节）。"""

    model_id: str
    display_name: str
    license: str
    size_hint: str
    downloaded: bool


@dataclass(frozen=True)
class SpeakerInfo:
    """云端 TTS 音色摘要（前端展示用）。"""

    speaker_id: str
    display_name: str


class LiveHelperService(ABC):
    """前端服务接口。"""

    # ── 偏好配置 ──

    @abstractmethod
    def get_preferences(self) -> Preferences:
        """返回服务持有的偏好对象（同一引用，修改后调 save_preferences）。"""

    @abstractmethod
    def save_preferences(self) -> None:
        """持久化当前偏好（身份码/开关/阈值等）。"""

    @abstractmethod
    def warnings(self) -> list[str]:
        """配置体检：返回需要 UI 提示的问题（如云端 TTS 密钥未配置）。"""

    # ── 生命周期 ──

    @abstractmethod
    def start(self) -> None:
        """启动服务：连接弹幕源并进入事件循环。非阻塞，失败抛 ServiceError。"""

    @abstractmethod
    def stop(self, timeout: float = 10.0) -> None:
        """停止服务：断开连接、排空资源。幂等。"""

    @abstractmethod
    def is_running(self) -> bool:
        """服务是否运行中。"""

    # ── 事件流（互动面板等前端展示用）──

    @abstractmethod
    def subscribe_events(self, callback: EventCallback) -> None:
        """订阅统一事件流（所有事件，不受播报开关过滤）。可重复注册。"""

    @abstractmethod
    def unsubscribe_events(self, callback: EventCallback) -> None:
        """取消订阅。"""

    # ── 本地 TTS 模型管理 ──

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """可用本地模型列表及下载状态。"""

    @abstractmethod
    def list_cloud_speakers(self) -> list[SpeakerInfo]:
        """可用云端 TTS 音色列表（顺序即 UI 展示顺序）。"""

    @abstractmethod
    async def download_model(self, model_id: str, progress: ProgressCallback | None = None) -> None:
        """下载指定模型（异步，progress 回调报告进度）。未知模型抛 ServiceError。"""
