"""AIME 后端主程序入口。

启动 UIA 上下文看门狗线程和 TCP 服务器，支持 Ctrl+C 优雅退出。
启动顺序：配置加载 → 日志初始化 → 记忆模块 → 大模型加载 → 看门狗 → TCP 服务器。
"""

import signal
import sys
import threading
import time

from config import get_config
from core.logger import setup_logger, shutdown_logger, get_logger
from core.shutdown import set_shutdown, is_shutdown
from core.context import context_watchdog_worker
from core.context import uia_context
from core.inference import init_model
from core.server import start_tcp_server
from core.memory import init_memory, shutdown_memory, get_stats


def _handle_signal(signum, frame):
    """处理系统信号，触发全局优雅退出。

    Args:
        signum: 信号编号 (SIGINT / SIGTERM)。
        frame: 当前栈帧对象（未使用）。
    """
    print("\n⏳ 正在安全关闭所有线程，请稍候...")
    set_shutdown()


def debug_context_status():
    """调试线程：每 2 秒打印一次 UIA 上下文状态。"""
    while not is_shutdown():
        ctx = uia_context.GLOBAL_CONTEXT
        print(f"🔍 [调试] GLOBAL_CONTEXT = '{ctx[:50] if ctx else '(空)'}'")
        time.sleep(2)


def main():
    """程序主入口，按顺序初始化各模块并启动 TCP 服务器。"""
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    app_cfg = get_config()

    log_cfg = app_cfg.logging
    setup_logger(log_cfg.dir, log_cfg.file, log_cfg.level)
    _log = get_logger()
    _log.info("AIME 后端启动")

    try:
        init_memory()
        stats = get_stats()
        _log.info(f"记忆模块就绪: {stats['total_records']} 条记录")
    except Exception as e:
        _log.error(f"记忆模块初始化失败: {e}")

    try:
        init_model()
    except Exception as e:
        _log.error(f"模型初始化失败: {e}")
        sys.exit(1)

    watchdog = threading.Thread(target=context_watchdog_worker, daemon=True, name="watchdog")
    watchdog.start()

    debug_thread = threading.Thread(target=debug_context_status, daemon=True, name="debug")
    debug_thread.start()

    try:
        start_tcp_server()
    except KeyboardInterrupt:
        pass

    _log.info("AIME 后端正在退出...")
    shutdown_memory()
    shutdown_logger()
    print("👋 AIME 后端已安全关闭")


if __name__ == "__main__":
    main()
