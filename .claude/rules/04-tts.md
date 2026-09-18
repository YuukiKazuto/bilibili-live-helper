# 04 — TTS 模块设计

> 上级文档：[../../CLAUDE.md](../../CLAUDE.md)。配置读取见 [03-config-secrets.md](03-config-secrets.md)，播报文案见 [02-features.md](02-features.md)。

## 双模式切换

UI 提供「本地 TTS / 云端 TTS」模式切换，`tts/base.py` 定义 `TTSProvider` 抽象基类，两种实现可插拔（架构见 [01-architecture.md](01-architecture.md)）。

### 1. 本地 TTS

- 支持下载高质量本地语音模型。
- 模型下载来源由开发时自行检索并**评估合法性与可用性**（许可协议允许商用/分发）后接入。
- 模型文件目录加入 `.gitignore`（大文件不入库）。

#### 本地 TTS 实现选型（2026-09 已定）

- **默认：系统自带 TTS**，零下载开箱即用。macOS 走 `say`（自动发现 `zh_*` 中文音色），Windows 走 PowerShell `System.Speech`（按 `VoiceInfo.Culture` 匹配 `zh-*`）。实现在 `tts/local/system_tts.py`。
- **可下载模型（免费可商用，已核实许可）**，推理引擎统一为 sherpa-onnx（Apache-2.0，CPU 实时，无需 PyTorch），实现在 `tts/local/sherpa_tts.py`：
  - 轻量：**MeloTTS zh_en**（MIT，约 170MB，CPU 实时，中英混读）
  - 中量/音质优先：**Kokoro-82M**（`kokoro-multi-lang-v1_1`，Apache-2.0，约 310MB，中英 103 音色）
  - 淘汰：Piper（新版引擎 GPL-3.0 商用受限）、ChatTTS（CC BY-NC 禁商用）、CosyVoice/IndexTTS（GB 级需 GPU）
- **模型注册表与下载**在 `tts/local/model_manager.py`：多源依次尝试（GitHub release 压缩包 → hf-mirror.com 按文件下载回退，应对国内网络），下载后校验必需文件，失败清理残留。
- **模型选择**存于用户偏好 `tts_local_model`（`"system"` 或注册表 `model_id`，见 `config/preferences.py`）；模型未下载/未知时回退系统 TTS 并记日志。
- **模型存储目录（2026-09 定，配合 exe 打包）**：
  - 默认**用户数据目录**：Windows `%LOCALAPPDATA%/bilibili-live-helper/models`，macOS `~/Library/Application Support/bilibili-live-helper/models`，Linux `~/.local/share/bilibili-live-helper/models`——安装到 Program Files 等只读目录后依然可写。
  - 便携版例外：安装/解压目录**可写时**（探测有写权限）允许下载到安装目录下 `models/`，实现「绿色免安装」；不可写则自动回退用户数据目录并记日志。
  - 用户偏好可显式配置 `models_dir` 覆盖默认解析。
  - 开发模式（源码运行）仍可用项目根 `models/`（`.gitignore` 已覆盖），便于调试。

### 2. 云端 TTS

- API 密钥从**项目配置文件**读取，**不读取系统环境变量**，由使用者自行填写配置（见 [03-config-secrets.md](03-config-secrets.md)）。
- 密钥缺失时给出明确 UI 提示，不得静默失败或回退读取系统环境变量。

## 订阅制预留（第二阶段）

项目上线为直播姬 H5 插件后，云端 TTS 采用**订阅制收费**：

- `cloud_tts.py` 中预留计费/鉴权扩展接口（如订阅态校验、用量上报钩子），第一阶段可为空实现，但接口形态需先定义好。
