"""密钥与常驻配置加载。

规则（.claude/rules/03-config-secrets.md）：
- 所有密钥（B站开放平台、云端 TTS、后续大模型等）从项目配置文件读取，禁止硬编码。
- 使用 load_dotenv 加载 .env 到程序环境变量。
- 真实配置文件不入 Git，仅 .example 入库。
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录
ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    """密钥与常驻配置（非用户偏好）。"""

    # B站开放平台
    bili_app_id: int = 0
    bili_access_key: str = ""
    bili_access_secret: str = ""
    bili_api_host: str = "https://live-open.biliapi.net"

    # 云端 TTS（密钥只从配置文件来，不读系统环境变量；接入规范见 rules/06）
    tts_cloud_api_key: str = ""
    tts_cloud_speaker: str = "zh_female_vv_uranus_bigtts"

    # 后续新增大模型等密钥在此扩展

    def validate(self) -> list[str]:
        """返回缺失项列表，供 UI 提示。"""
        missing = []
        if not self.bili_app_id:
            missing.append("bili_app_id")
        if not self.bili_access_key:
            missing.append("bili_access_key")
        if not self.bili_access_secret:
            missing.append("bili_access_secret")
        return missing


def load_settings(env_file: str = ".env", config_file: str = "config.json") -> Settings:
    """加载配置：优先 .env（load_dotenv），其次 config.json，合并为 Settings。

    主播身份码不在此处 —— 它是用户在 UI 填写并持久化的偏好（见 preferences.py）。
    """
    load_dotenv(ROOT_DIR / env_file)

    settings = Settings(
        bili_app_id=int(os.getenv("BILI_APP_ID", "0") or 0),
        bili_access_key=os.getenv("BILI_ACCESS_KEY", ""),
        bili_access_secret=os.getenv("BILI_ACCESS_SECRET", ""),
        bili_api_host=os.getenv("BILI_API_HOST", Settings.bili_api_host),
        tts_cloud_api_key=os.getenv("TTS_CLOUD_API_KEY", ""),
        tts_cloud_speaker=os.getenv(
            "TTS_CLOUD_SPEAKER", Settings.tts_cloud_speaker
        ),
    )

    # config.json 作为可选补充（优先级低于环境变量已存在的值）
    path = ROOT_DIR / config_file
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        for k, v in data.items():
            if hasattr(settings, k) and not getattr(settings, k):
                setattr(settings, k, v)

    return settings
