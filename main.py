"""B站直播弹幕播报辅助工具 — 程序入口。

默认启动 PySide6 桌面 UI；`--cli` 走命令行前台模式（调试用）。
两种前端都只依赖 service 接口（rules/01「两阶段架构」）。
"""
import argparse
import time

from service.local import LocalLiveService
from utils.logging_setup import setup_logging


def run_cli(service: LocalLiveService) -> None:
    """命令行前台运行：Ctrl+C 优雅退出。"""
    service.start()  # 身份码未填写等业务错误抛 ServiceError
    try:
        while service.is_running():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="B站直播弹幕播报辅助工具")
    parser.add_argument("--cli", action="store_true", help="命令行模式（不启动 UI）")
    args = parser.parse_args()

    setup_logging()
    service = LocalLiveService()

    if args.cli:
        run_cli(service)
        return

    from ui.app import run_app  # 延迟导入：--cli 模式无需加载 PySide6

    try:
        code = run_app(service)
    finally:
        service.stop()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
