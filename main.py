"""B站直播弹幕播报辅助工具 — 程序入口（阶段 1）。

命令行前台运行：启动服务（后台线程跑核心链路），Ctrl+C 优雅退出。
PySide6 前端（另一分支）同样只依赖 service 接口，替换本文件的运行方式。
"""
import time

from service.local import LocalLiveService
from utils.logging_setup import setup_logging


def main() -> None:
    setup_logging()

    service = LocalLiveService()
    service.start()  # 身份码未填写等业务错误抛 ServiceError

    try:
        while service.is_running():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()


if __name__ == "__main__":
    main()
