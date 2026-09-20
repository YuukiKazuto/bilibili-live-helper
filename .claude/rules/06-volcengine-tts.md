# 06 — 火山引擎云端 TTS 接入规范（豆包语音）

> 上级文档：[../../CLAUDE.md](../../CLAUDE.md)。TTS 双模式设计见 [04-tts.md](04-tts.md)。
> 依据官方文档整理：单向流式语音合成 WebSocket（豆包语音 / 大模型语音合成 V3）。

## 协议选型（已定）

| 方案 | 结论 |
|------|------|
| HTTP 单向流式 | 每条播报完整 HTTP 连接开销，不采用 |
| **单向流式 WebSocket** | ✅ 采用：一次性输入文本、流式返回音频，与播报场景一致；无连接状态，失败直接重试 |
| 双向流式 WebSocket | 文本流式输入 + 长连接多 session，对短句播报收益小、复杂度高；作为后续延迟优化备选 |

## 接入要点

- **端点**：`wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream`
  （接入参数——端点/资源 ID/采样率/声道数/默认音色——均经 `.env` 可配置，
  键名 `TTS_CLOUD_ENDPOINT` / `TTS_CLOUD_RESOURCE_ID` / `TTS_CLOUD_SAMPLE_RATE` /
  `TTS_CLOUD_CHANNELS` / `TTS_CLOUD_DEFAULT_SPEAKER`，见 `config/loader.py` Settings；
  代码内不写死，仅留内置默认值兜底）
- **鉴权（新版控制台）**：请求头
  - `X-Api-Key`：API Key，从控制台「API Key 管理」获取 → 存于项目配置文件 `TTS_CLOUD_API_KEY`（红线见 03/04）
  - `X-Api-Resource-Id`：`seed-tts-2.0`（豆包语音合成大模型 2.0）
  - `X-Api-Request-Id`：uuid，标识客户端请求
  - （旧版控制台为 `X-Api-App-Id` + `X-Api-Access-Key` 两头，如迁移再扩展）
- **⚠️ 二进制帧协议（官方文档正文只写 JSON，实测必须走二进制帧，官方 demo：`websocket unidirectional/protocols.py`）**
  - 实现：`tts/volcengine_proto.py`（encode_frame / decode_frame）
  - 帧头 4B：`[version(4b)|header_size(4b)][msg_type(4b)|flags(4b)][serialization(4b)|compression(4b)][reserved(8b)]`
  - 客户端请求：`FullClientRequest`(0x1) 帧 flag=NoSeq，4B 负载长度 + JSON 负载（`{"req_params": {...}}`）
    - **直接发 JSON 文本帧会被拒**：服务端按二进制帧解析，`{`(0x7B) 首字节高 4 位=7 → 报 `unsupported protocol version 7`
  - 服务端响应（全部为二进制帧，flag=WithEvent 时负载前带 4B 事件号 + 4B 会话 ID 长度 + 会话 ID）：
    - `AudioOnlyServer`(0xB)：裸音频块负载
    - `FullServerResponse`(0x9)：事件 `TTSSentenceStart=350` / `TTSSentenceEnd=351`（负载含识别文本）/ `SessionFinished=152`（负载含计费 usage）/ `SessionFailed=153`
    - `Error`(0xF)：4B 错误码 + JSON 错误信息
  - 会话结束后服务端不主动关连接，由客户端 `close()`
- **请求 JSON**：`{"req_params": {"text": "...", "speaker": "<音色ID>", "audio_params": {"format": "pcm", "sample_rate": 24000}}}`
  - `speaker`：音色 ID，默认 `zh_female_vv_uranus_bigtts`。**音色属用户偏好**
    （`Preferences.tts_cloud_speaker`），在 UI「设置 → 云端音色」下拉选择
    （注册表 `CLOUD_SPEAKERS` 于 `tts/cloud_tts.py`，经 `service.list_cloud_speakers()`
    提供给前端，rules/07「UI 复用约束」），**不再走 .env / Settings 配置**
  - 音频格式：**流式场景推荐 pcm**（不支持指定比特率），也可 mp3 / wav / ogg_opus；采样率 pcm/mp3/wav 默认 24000
  - 其他可选：`speech_rate` / `loudness_rate`（-50~100）、`ssml`、发音词典 `pronunciation_dict` 等，按需再接
- **播放**：PCM 裸流边收边播（sounddevice 输出流），收完等排空，保证 `speak()` 阻塞至播放完成的队列语义
- **计费用量**：请求头带 `X-Control-Require-Usage-Tokens-Return: *` 后，计费字数随 `SessionFinished(152)` 事件负载返回（实测 `{"usage":{"text_words":N}}`）→ 传入 `_charge_hook`（订阅制预留，见 04）
- **错误处理**：密钥缺失 → 明确提示不静默；连接/合成失败（Error 帧 / SessionFailed / 异常）→ 记日志跳过该条，不得中断播报循环
