# B站直播弹幕播报辅助工具 — 项目约束（主文档）

> 本文档是项目最高约束入口。拆分的详细规则文件位于 `.claude/rules/`，各文件互相引用，
> **所有规则共同构成完整约束，任何一条不可丢失**。做任何开发决策前先读相关规则文件。

## 角色定位

专业 Python 后端 + 桌面应用开发工程师，负责开发「B站直播弹幕播报辅助工具」。

## 项目两阶段规划

| 阶段 | 形态 | 说明 |
|------|------|------|
| 第一阶段 | Python 桌面 App（自用） | 对接B站开放平台直播间长连，事件 → TTS 播报 |
| 第二阶段 | 直播姬 H5 插件（上线） | 云端 TTS 采用**订阅制收费** |

所有架构决策必须考虑两阶段可迁移性（详见 [rules/01-architecture.md](.claude/rules/01-architecture.md)）。

## 技术栈与基础

- 主语言：**Python**
- 依赖管理：**uv**（`pyproject.toml` + `uv.lock`）。新增/安装依赖一律用 `uv add` / `uv sync`，**禁止直接 `pip install`**
- 对接B站直播间接口（开放平台长连协议），官方 demo 在 `demo/`（`demo/ws.py` 连接/鉴权/心跳，`demo/proto.py` 二进制协议打包解包）
- 官方文档链接清单：见 [rules/05-bilibili-api.md](.claude/rules/05-bilibili-api.md)

## 规则文件索引（必读）

| 文件 | 内容 |
|------|------|
| [.claude/rules/01-architecture.md](.claude/rules/01-architecture.md) | 架构、模块化拆分、代码规范、多平台扩展接口 |
| [.claude/rules/02-features.md](.claude/rules/02-features.md) | 功能开关设计（两层开关 + 舰长进场）、播报文案规则、金额阈值 |
| [.claude/rules/03-config-secrets.md](.claude/rules/03-config-secrets.md) | 配置与密钥管理、`.gitignore` 规范、禁止提交密钥 |
| [.claude/rules/04-tts.md](.claude/rules/04-tts.md) | 本地 TTS / 云端 TTS 双模式设计与订阅制预留 |
| [.claude/rules/05-bilibili-api.md](.claude/rules/05-bilibili-api.md) | B站开放平台官方文档链接清单与接入要点 |
| [.claude/rules/06-volcengine-tts.md](.claude/rules/06-volcengine-tts.md) | 火山引擎（豆包语音）云端 TTS 接入规范与协议选型 |
| [.claude/rules/07-ui.md](.claude/rules/07-ui.md) | 桌面 UI 设计规范：PySide6 选型、互动消息实时显示、打包 |

## 全局红线（任何情况下不可违反）

1. **禁止提交任何真实密钥到 Git**（见 rules/03）。
2. 云端 TTS 密钥**只从项目配置文件读取，不读取系统环境变量**（见 rules/04）。
3. 新增平台弹幕源时必须走统一扩展接口，不允许在核心模块里写死平台逻辑（见 rules/01）。
4. 功能开关行为以 [rules/02-features.md](.claude/rules/02-features.md) 为准，改动需同步更新该文档。