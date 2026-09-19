"""日志统一配置。"""
import logging
import os
import sys


def setup_logging(level: int | None = None) -> None:
    """初始化日志。level 未指定时读环境变量 LOG_LEVEL（默认 INFO）。"""
    if level is None:
        level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
