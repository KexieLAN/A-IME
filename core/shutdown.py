"""全局优雅退出事件。

所有后台线程通过 is_shutdown() / wait_shutdown() 检查是否应停止。
主线程通过 set_shutdown() 发出退出信号。
"""

import threading

_event = threading.Event()


def is_shutdown() -> bool:
    """检查是否已发出退出信号。

    Returns:
        True 表示应立即停止工作。
    """
    return _event.is_set()


def set_shutdown():
    """发出全局退出信号，所有等待中的线程将被唤醒。"""
    _event.set()


def wait_shutdown(timeout: float | None = None) -> bool:
    """阻塞等待退出信号或超时。

    Args:
        timeout: 最大等待秒数，None 表示永久等待。

    Returns:
        True 表示收到退出信号，False 表示超时。
    """
    return _event.wait(timeout)
