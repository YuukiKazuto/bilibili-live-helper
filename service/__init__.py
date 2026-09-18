"""服务接口层：前端（桌面 UI / 阶段 2 H5 插件）访问核心功能的唯一入口。

规则（.claude/rules/01-architecture.md「两阶段架构」）：
- 阶段 1：service.local 进程内实现；阶段 2：替换为 HTTP/WebSocket 客户端实现同一接口。
- UI 禁止直接 import core/platforms/tts，一律经本层（见 rules/07）。
"""
from service.base import LiveHelperService, ModelInfo, ServiceError

__all__ = ["LiveHelperService", "ModelInfo", "ServiceError"]
