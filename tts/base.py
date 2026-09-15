"""TTS Provider 抽象基类。"""
from abc import ABC, abstractmethod


class TTSProvider(ABC):
    """语音合成提供方接口：本地与云端实现可插拔。"""

    @abstractmethod
    async def speak(self, text: str) -> None:
        """合成并播放一段文本（阻塞至播放完成，保证播报顺序）。"""

    @abstractmethod
    async def close(self) -> None:
        """释放资源。"""
