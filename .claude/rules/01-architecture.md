# 01 — 架构与代码规范

> 上级文档：[../../CLAUDE.md](../../CLAUDE.md)。功能开关见 [02-features.md](02-features.md)，配置密钥见 [03-config-secrets.md](03-config-secrets.md)，TTS 见 [04-tts.md](04-tts.md)，B站接口见 [05-bilibili-api.md](05-bilibili-api.md)。

## 总体架构（第一阶段 Python 桌面 App）

按 Python 工程化标准模块化拆分，建议结构（可按实际微调，但层次不变）：

```
bilibili_live_helper/
├── main.py                  # 程序入口
├── core/
│   ├── event_bus.py         # 事件总线：弹幕源 → 播报策略 → TTS 的解耦中枢
│   └── broadcaster.py       # 播报策略：开关过滤 + 文案生成（规则见 02-features.md）
├── platforms/               # 多平台弹幕源（扩展接口）
│   ├── base.py              # PlatformBase 抽象基类
│   └── bilibili/            # B站实现（连接/鉴权/心跳/事件解析，参考 demo/ws.py）
├── tts/                     # TTS 模块（规则见 04-tts.md）
│   ├── base.py              # TTSProvider 抽象基类
│   ├── local_tts.py         # 本地 TTS
│   └── cloud_tts.py         # 云端 TTS
├── config/                  # 配置加载（规则见 03-config-secrets.md）
├── ui/                      # 桌面 UI（开关勾选、阈值输入框、TTS 模式切换）
└── utils/
```

## 核心解耦原则

1. **事件流单向**：弹幕源（platforms）→ 事件总线（event_bus）→ 播报策略（broadcaster）→ TTS。
2. **平台无关**：播报策略和 TTS 不感知任何B站特有字段；平台适配层负责把平台事件归一化为内部统一事件模型。
3. **UI 与逻辑分离**：开关/阈值等 UI 状态持久化为用户配置，逻辑层只读配置，不直接依赖 UI 控件。

## 多平台扩展接口（预留）

`platforms/base.py` 定义抽象基类，所有弹幕源（含未来的其他平台）实现：

- `connect()` / `close()` — 生命周期
- `events` — 异步事件流，产出**统一事件模型**（如：弹幕、礼物、进场、关注、上舰、醒目留言、点赞等归一化类型 + 统一用户昵称/金额字段）
- 新增平台 = 新增一个 `platforms/<name>/` 包实现基类，**禁止**在 core/ 或 tts/ 中出现平台分支判断。

## 两阶段可迁移性

- 第二阶段改造为直播姬 H5 插件：核心播报策略（core/broadcaster）与文案规则必须保持纯逻辑、无桌面 UI/音频设备依赖，便于直接移植到 H5/服务端。
- 云端 TTS 层预留订阅制计费接口（详见 [04-tts.md](04-tts.md)）。

## 代码规范

- 模块化拆分，职责单一；公共逻辑下沉 utils/。
- 注释清晰：模块级 docstring 说明职责，关键协议解析/签名逻辑（如B站 HMAC-SHA256 签名）必须配注释。
- 预留扩展接口（平台源、TTS Provider、计费）均为抽象基类 + 注册机制。
- 类型注解 + 遵循 PEP 8。
