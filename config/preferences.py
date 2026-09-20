"""用户偏好持久化：功能开关、金额阈值、TTS 模式、主播身份码。

规则：
- 身份码不是密钥：由主播在 UI 填写，保存到本地（类似存 JWT），打开应用自动填充
  （见 .claude/rules/03-config-secrets.md「主播身份码例外」）。
- 开关与文案规则见 .claude/rules/02-features.md。
- 用户偏好与密钥分文件存放；本文件内容属于个人数据，不入 Git。
"""
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

# 打包后 exe 旁边的用户偏好文件（源码运行 = 项目根，见 utils/app_paths.py）
from utils.app_paths import app_root

PREFS_PATH = app_root() / "user_preferences.json"


@dataclass
class Preferences:
    """用户偏好（UI 可编辑，本地持久化）。"""

    # ── 第一层：播报开关（勾选即播报事件原文）──
    broadcast_danmaku: bool = False        # 弹幕
    broadcast_gift: bool = False           # 礼物投喂
    broadcast_super_chat: bool = False     # 醒目留言
    broadcast_entry: bool = False          # 进场消息
    broadcast_follow: bool = False         # 关注通知
    broadcast_guard: bool = False          # 大航海上舰
    broadcast_like: bool = False           # 点赞

    # ── 第二层：附加感谢播报开关（独立可选）──
    thanks_gift: bool = False              # 礼物投喂感谢
    thanks_super_chat: bool = False        # 醒目留言感谢
    thanks_follow: bool = False            # 关注通知感谢（⚠ 协议无此事件，见 rules/05）
    thanks_guard: bool = False             # 大航海上舰感谢
    thanks_like: bool = False              # 点赞感谢

    # ── 独立可选开关 ──
    guard_entry_welcome: bool = False      # 舰长进场播报

    # ── 文案阈值 ──
    amount_threshold: float = 50.0         # 金额阈值（元），默认 50

    # ── TTS 模式：local / cloud ──
    tts_mode: str = "local"
    # 本地 TTS 模型选择："system"=系统自带；否则为 tts/local/model_manager.py 注册表中的 model_id
    tts_local_model: str = "system"
    # 云端 TTS 音色（UI 下拉选择，注册表见 tts/cloud_tts.py CLOUD_SPEAKERS）
    # 空 = 未选择，运行时回退 .env 的 TTS_CLOUD_DEFAULT_SPEAKER（再退内置默认）
    tts_cloud_speaker: str = ""
    # 本地模型存放目录：留空按 rules/04 自动解析（用户数据目录/便携安装目录/开发目录）
    models_dir: str = ""

    # ── 主播身份码（UI 填写，自动填充）──
    bili_id_code: str = ""


class PreferenceStore:
    """Preferences 的加载/保存。"""

    @staticmethod
    def load(path: Path = PREFS_PATH) -> Preferences:
        if not path.exists():
            return Preferences()
        data = json.loads(path.read_text(encoding="utf-8"))
        # 只接受 Preferences 已定义的字段，忽略未知键
        valid = {f.name for f in Preferences.__dataclass_fields__.values()}
        return Preferences(**{k: v for k, v in data.items() if k in valid})

    @staticmethod
    def save(prefs: Preferences, path: Path = PREFS_PATH) -> None:
        path.write_text(
            json.dumps(asdict(prefs), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
