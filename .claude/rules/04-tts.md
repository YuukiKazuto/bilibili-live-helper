# 04 — TTS 模块设计

> 上级文档：[../../CLAUDE.md](../../CLAUDE.md)。配置读取见 [03-config-secrets.md](03-config-secrets.md)，播报文案见 [02-features.md](02-features.md)。

## 双模式切换

UI 提供「本地 TTS / 云端 TTS」模式切换，`tts/base.py` 定义 `TTSProvider` 抽象基类，两种实现可插拔（架构见 [01-architecture.md](01-architecture.md)）。

### 1. 本地 TTS

- 支持下载高质量本地语音模型。
- 模型下载来源由开发时自行检索并**评估合法性与可用性**（许可协议允许商用/分发）后接入。
- 模型文件目录加入 `.gitignore`（大文件不入库）。

### 2. 云端 TTS

- API 密钥从**项目配置文件**读取，**不读取系统环境变量**，由使用者自行填写配置（见 [03-config-secrets.md](03-config-secrets.md)）。
- 密钥缺失时给出明确 UI 提示，不得静默失败或回退读取系统环境变量。

## 订阅制预留（第二阶段）

项目上线为直播姬 H5 插件后，云端 TTS 采用**订阅制收费**：

- `cloud_tts.py` 中预留计费/鉴权扩展接口（如订阅态校验、用量上报钩子），第一阶段可为空实现，但接口形态需先定义好。
