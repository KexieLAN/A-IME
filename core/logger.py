"""异步日志模块。

使用 QueueHandler + QueueListener 实现非阻塞日志写入，
避免频繁磁盘 I/O 阻塞推理线程。
日志同时写入文件（RotatingFileHandler，UTF-8）和控制台。
"""

import logging
import logging.handlers
from queue import Queue
from pathlib import Path

_log_queue: Queue = Queue(-1)
_listener: logging.handlers.QueueListener | None = None
_logger: logging.Logger | None = None


def setup_logger(log_dir: str, log_file: str, level: str = "INFO"):
    """初始化异步日志系统。

    创建日志目录、配置 RotatingFileHandler 和控制台 Handler，
    通过 QueueListener 在后台线程中异步写入。

    Args:
        log_dir: 日志文件存放目录。
        log_file: 日志文件名。
        level: 日志级别，可选 DEBUG / INFO / WARNING / ERROR。
    """
    global _listener, _logger

    Path(log_dir).mkdir(parents=True, exist_ok=True)

    _logger = logging.getLogger("aime")
    _logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    _logger.propagate = False

    queue_handler = logging.handlers.QueueHandler(_log_queue)
    _logger.addHandler(queue_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        Path(log_dir) / log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-5s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-5s | %(message)s",
        datefmt="%H:%M:%S",
    ))

    _listener = logging.handlers.QueueListener(
        _log_queue, file_handler, console, respect_handler_level=True
    )
    _listener.start()


def shutdown_logger():
    """停止日志监听线程，确保队列中的日志全部写入。"""
    if _listener:
        _listener.stop()


def get_logger() -> logging.Logger:
    """获取全局 Logger 实例。

    Returns:
        logging.Logger: 已初始化的 Logger 对象。

    Raises:
        RuntimeError: 日志系统未初始化时抛出。
    """
    if _logger is None:
        raise RuntimeError("日志系统未初始化，请先调用 setup_logger()")
    return _logger


def log_model(msg: str):
    """记录模型相关事件（加载、就绪、异常）。

    Args:
        msg: 日志消息内容。
    """
    get_logger().info(f"[模型] {msg}")


def log_inference(pinyin: str, duration_ms: float, phase: str = "", word: str = ""):
    """记录单次推理耗时和结果。

    Args:
        pinyin: 用户输入的拼音。
        duration_ms: 推理耗时（毫秒）。
        phase: 推理阶段标识（L1 / Phase1 / Phase2），可选。
        word: 生成或选中的候选词，可选。
    """
    extra = f" | phase={phase}" if phase else ""
    extra += f" | word={word}" if word else ""
    get_logger().info(f"[推理] pinyin={pinyin} | {duration_ms:.1f}ms{extra}")


def log_error(msg: str):
    """记录错误级别日志。

    Args:
        msg: 错误描述信息。
    """
    get_logger().error(f"[错误] {msg}")


def log_warning(msg: str):
    """记录警告级别日志。

    Args:
        msg: 警告描述信息。
    """
    get_logger().warning(f"[警告] {msg}")
