# 05 — B站开放平台接口与文档链接

> 上级文档：[../../CLAUDE.md](../../CLAUDE.md)。官方 demo 在 `demo/`（`ws.py` 长连建立/鉴权/心跳，`proto.py` 二进制协议打包解包），接入实现以官方文档为准，demo 仅作参考。

## 官方文档链接清单

1. 应用api列表：https://open-live.bilibili.com/document/eba8e2e1-847d-e908-2e5c-7a1ec7d9266f#h1--api
2. 长连数据协议说明：https://open-live.bilibili.com/document/657d8e34-f926-a133-16c0-300c1afc6e6b#h1-u957Fu94FEu6570u636Eu534Fu8BAEu8BF4u660E
3. 直播间数据：https://open-live.bilibili.com/document/f9ce25be-312e-1f4a-85fd-fef21f1637f8#h1-u76F4u64ADu95F4u6570u636E
4. 互动面板：https://open-live.bilibili.com/document/ba5bdccd-3096-d9eb-baee-d1b224f3c5f2#h1-u4E92u52A8u9762u677F
5. 定制面板：https://open-live.bilibili.com/document/bf5e438f-3bce-3c8c-3bd4-e9526ace16ec#h2-u81EAu5B9Au4E49u9875u9762
6. 定制面板接口：https://open-live.bilibili.com/document/ea150c95-ed18-ed1c-6f8e-72ce6ddea962#h2-u63A5u53E3u6587u6863
7. 订阅扩展DLC：https://open-live.bilibili.com/document/8fab0079-def7-56f0-8b52-49f2167d6b11#h2--dlc-
8. 拓展接口说明：https://open-live.bilibili.com/document/b887f3ef-855e-b313-9b24-9e3cdd6cb827#h2-u62D3u5C55u63A5u53E3u8BF4u660E
9. 订阅记录查询：https://open-live.bilibili.com/document/f7dddeae-f47c-b5b5-0173-c9784ba38ee1#h1-u8BA2u9605u8BB0u5F55u67E5u8BE2
10. QA：https://open-live.bilibili.com/document/63a33aa9-1f6f-a33c-cd8a-30dcc43db16d#h2--qa-

（用户会按需补充更多文档链接；新增时更新本清单。）

## 接入要点（基于 demo）

- 线上环境 host：`https://live-open.biliapi.com`（2026-09-19 实测：`live-open.biliapi.net` 无法 DNS 解析，弃用；与 demo 一致）。
- HTTP 签名：`x-bili-*` 请求头按字典序拼接后 HMAC-SHA256（见 `demo/ws.py` 的 `sign()`，实现时需配注释）。
- 长连流程：`/v2/app/start` 获取 wss 地址与 auth_body → WebSocket 连接 → 发送鉴权包（op=7）→ 每 20s 心跳（op=2）+ 应用心跳（`/v2/app/heartbeat`）→ 退出时 `/v2/app/end`。
- **长连必须 `ping_interval=None` 禁用 websockets 内建 keepalive**（2026-09-19 实测：B站
  comet 服务器不回复协议层 PING，连接固定 ~50s 后被库判超时自杀 CLOSE 1011，
  表现为「收到少量事件后全部断流」）；保活仅依赖 B站自有 op=2 应用层心跳。
- 二进制协议：大端 16 字节包头（packetLen/ver/op/seq），见 `demo/proto.py`。
- 事件字段以官方文档为准（2026-09-19 逐字段核对，此前有臆造错误）：
  - CMD 名称：进场是 `LIVE_OPEN_PLATFORM_LIVE_ROOM_ENTER`（非 LIVE_ENTER_ROOM）；
    上舰是 `LIVE_OPEN_PLATFORM_GUARD`（非 GUARD_BUY）——错误 CMD 不会触发任何事件。
  - 礼物 `SEND_GIFT`：数量字段是 **`gift_num`**（非 amount）；`price`/`r_price` 单位为
    **金瓜子**（1000 = 1元 = 10电池，实测 0.1 元人气票 price=100）；`r_price` 为实际价值
    优先采用；盲盒 `blind_gift.status=true`，`gift_name` 为爆出道具名，播报直接
    「盲盒爆出的 xx」（不做盒名映射）。
  - 上舰 `GUARD`：昵称在 `user_info.uname`（嵌套）；数量字段 `guard_num`。
  - 醒目留言 `SUPER_CHAT`：金额字段是 **`rmb`（单位已是元）**，非 price。
  - 其他可用 CMD（暂未处理，按需扩展）：`LIVE_START/END`（开播/下播）、
    `INTERACTION_END`（game_id 失效）、`SUPER_CHAT_DEL`、`DM_MIRROR`。
- 协议限制（2026-09-19 文档核对，不是代码问题）：
  - **长连协议没有「关注」事件**（11 个 CMD 中无 FOLLOW）——「关注通知/感谢关注」
    开关在开放平台下收不到事件，属预期行为。
  - **点赞仅在开播中触发**，且来源是**移动端 APP 双击画面**（网页点赞不推），
    单一用户 2 秒内聚合为一条（`like_count`）。
- 密钥（access_key/access_key_secret/app_id）来自项目配置文件；主播身份码由主播在 UI 填写并本地持久化（阶段 1），阶段 2 插件内直接获取（详见 [03-config-secrets.md](03-config-secrets.md)）。
- 事件解析归一化为统一事件模型后进入事件总线（见 [01-architecture.md](01-architecture.md)），事件与播报开关的映射见 [02-features.md](02-features.md)。
