# B站直播弹幕播报辅助工具

阶段 1：Python 桌面 App（自用）；阶段 2：直播姬 H5 插件（云端 TTS 订阅制）。
完整项目约束见 `CLAUDE.md` 与 `.claude/rules/`。

## 快速开始

```bash
uv sync
cp .env.example .env      # 填入B站开放平台密钥
uv run main.py            # 身份码/开关等在 UI 中配置（骨架阶段暂用 user_preferences.json）
```

## 结构

```
main.py              入口
config/              密钥配置加载 + 用户偏好持久化（开关/阈值/身份码）
core/                事件总线 + 播报策略（纯逻辑，可移植）
platforms/           弹幕源：base 统一事件模型；bilibili/ B站长连实现
tts/                 本地/云端 TTS（TTSProvider 可插拔，订阅制预留）
ui/                  桌面界面（骨架）
demo/                B站官方 demo（仅参考）
```
