"""桌面 UI 骨架（阶段 1）。

职责（对应 .claude/rules/02-features.md 与 03-config-secrets.md）：
- 第一层 7 项播报开关 + 第二层 4 项感谢开关 + 舰长进场开关
- 金额阈值输入框（默认 50 元）
- TTS 模式切换（本地/云端）
- 主播身份码填写 + 保存（本地持久化，打开应用自动填充）
- 密钥缺失提示（如云端 TTS 密钥未配置）

实现待定：UI 框架选型后填充；逻辑层只依赖 Preferences 对象，UI 不进入核心链路。
"""


class AppSkeleton:
    """UI 入口占位：加载偏好 → 渲染界面 → 变更写回 PreferenceStore。"""

    def __init__(self) -> None:
        # TODO: UI 框架实现
        pass
