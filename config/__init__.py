"""配置加载器。

提供 YAML 配置文件的单例加载和类型安全访问。
首次调用 get_config() 时从 config/config.yaml 加载并缓存，
后续调用直接返回缓存实例。支持通过 reload_config() 热更新。
"""

from pathlib import Path
from dataclasses import dataclass, field

import yaml

_CONFIG_DIR = Path(__file__).parent
_CONFIG_PATH = _CONFIG_DIR / "config.yaml"

_CONFIG = None


@dataclass
class ModelConfig:
    """大模型加载配置。"""

    path: str = ""
    n_ctx: int = 32768
    n_gpu_layers: int = -1


@dataclass
class ServerConfig:
    """TCP 服务器配置。"""

    host: str = "127.0.0.1"
    port: int = 5000
    buffer_size: int = 4096


@dataclass
class ContextConfig:
    """UIA 上下文抓取配置。"""

    max_chars: int = 150
    poll_interval: float = 0.5
    uia_timeout: float = 0.3


@dataclass
class InferenceConfig:
    """两阶段推理引擎配置。"""

    short_context_chars: int = 100
    max_candidates: int = 5
    temperature: float = 0.0
    max_tokens: int = 6
    stop_tokens: list = field(default_factory=lambda: ["\n", "。", "，", "、"])
    phase2_min_pinyin_len: int = 3
    pinyin_threshold: float = 0.60
    max_generated_word_len: int = 5


@dataclass
class LoggingConfig:
    """异步日志配置。"""

    level: str = "INFO"
    dir: str = "logs"
    file: str = "aime.log"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 3


@dataclass
class MemoryConfig:
    """SQLite 记忆体系配置。"""

    db_path: str = "data/memory.db"
    max_records: int = 10000
    max_age_days: int = 30
    cleanup_interval: int = 3600
    context_hash_len: int = 50


@dataclass
class AppConfig:
    """应用全局配置聚合。"""

    model: ModelConfig = field(default_factory=ModelConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    inference: InferenceConfig = field(default_factory=InferenceConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)


def _load_config() -> AppConfig:
    """从 config.yaml 加载配置并构造 AppConfig 实例。

    Returns:
        AppConfig: 解析后的全局配置对象。

    Raises:
        FileNotFoundError: 配置文件不存在时抛出。
    """
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"配置文件不存在: {_CONFIG_PATH}\n"
            f"请确保 config/config.yaml 已正确创建"
        )

    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raw = {}

    return AppConfig(
        model=ModelConfig(**raw.get("model", {})),
        server=ServerConfig(**raw.get("server", {})),
        context=ContextConfig(**raw.get("context", {})),
        inference=InferenceConfig(**raw.get("inference", {})),
        logging=LoggingConfig(**raw.get("logging", {})),
        memory=MemoryConfig(**raw.get("memory", {})),
    )


def get_config() -> AppConfig:
    """获取全局配置单例。

    首次调用时从 YAML 文件加载，后续直接返回缓存。

    Returns:
        AppConfig: 全局配置对象。
    """
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = _load_config()
    return _CONFIG


def reload_config() -> AppConfig:
    """重新加载配置文件，覆盖缓存。

    Returns:
        AppConfig: 重新加载后的全局配置对象。
    """
    global _CONFIG
    _CONFIG = _load_config()
    return _CONFIG
