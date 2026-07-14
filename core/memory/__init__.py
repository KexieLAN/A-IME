"""SQLite 极简记忆体系模块。

实现 L1 Cache 查询、纠错捕获、LRU 淘汰。
写入操作通过异步队列和后台线程完成，避免阻塞推理线程。
"""

import hashlib
import sqlite3
import threading
import time
from pathlib import Path
from queue import Queue

from config import get_config
from core.logger import get_logger

_app_cfg = get_config()


def _get_memory_cfg():
    """获取记忆配置（支持热更新）。

    Returns:
        MemoryConfig 实例。
    """
    return _app_cfg.memory


_local = threading.local()
_write_queue: Queue = Queue(-1)
_writer_thread: threading.Thread | None = None
_writer_running: bool = False


def _get_db() -> sqlite3.Connection:
    """获取线程本地的 SQLite 数据库连接。

    首次调用时创建连接并配置 WAL 模式和 NORMAL 同步级别。

    Returns:
        线程本地的 sqlite3.Connection 实例。
    """
    if not hasattr(_local, "db") or _local.db is None:
        cfg = _get_memory_cfg()
        db_path = Path(cfg.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _local.db = sqlite3.connect(str(db_path), timeout=5.0)
        _local.db.execute("PRAGMA journal_mode=WAL")
        _local.db.execute("PRAGMA synchronous=NORMAL")
    return _local.db


def _init_db():
    """初始化数据库表结构和索引。"""
    db = _get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            context_hash TEXT NOT NULL,
            pinyin TEXT NOT NULL,
            correct_word TEXT NOT NULL,
            created_at REAL NOT NULL,
            last_used REAL NOT NULL,
            use_count INTEGER DEFAULT 1,
            UNIQUE(context_hash, pinyin, correct_word)
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_corrections_lookup
        ON corrections(context_hash, pinyin)
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_corrections_last_used
        ON corrections(last_used)
    """)
    db.commit()


def _hash_context(context: str) -> str:
    """对上下文进行 MD5 哈希，取后 context_hash_len 个字符作为特征。

    Args:
        context: 原始上下文文本。

    Returns:
        16 位十六进制哈希字符串。
    """
    cfg = _get_memory_cfg()
    short = context[-cfg.context_hash_len:] if len(context) > cfg.context_hash_len else context
    return hashlib.md5(short.encode("utf-8")).hexdigest()[:16]


def query(context: str, pinyin: str) -> str | None:
    """L1 Cache 查询：根据上下文和拼音查找历史纠错记录。

    命中时自动更新 last_used 和 use_count。

    Args:
        context: 当前上下文文本。
        pinyin: 用户输入的拼音。

    Returns:
        命中的正确候选词，未命中返回 None。
    """
    if not context.strip() or not pinyin.strip():
        return None

    try:
        ctx_hash = _hash_context(context)
        db = _get_db()

        cursor = db.execute(
            """
            SELECT correct_word, use_count
            FROM corrections
            WHERE context_hash = ? AND pinyin = ?
            ORDER BY use_count DESC, last_used DESC
            LIMIT 1
            """,
            (ctx_hash, pinyin)
        )

        row = cursor.fetchone()
        if row:
            word, count = row
            db.execute(
                """
                UPDATE corrections
                SET last_used = ?, use_count = use_count + 1
                WHERE context_hash = ? AND pinyin = ? AND correct_word = ?
                """,
                (time.time(), ctx_hash, pinyin, word)
            )
            db.commit()
            get_logger().debug(f"[记忆] L1 命中: {word} (count={count+1})")
            return word

        return None

    except Exception as e:
        get_logger().error(f"[记忆] 查询异常: {e}")
        return None


def record_correction(context: str, pinyin: str, correct_word: str):
    """记录用户纠错行为（异步写入队列）。

    当用户选择非 AI 推荐的词时调用，数据由后台线程批量写入数据库。

    Args:
        context: 当前上下文文本。
        pinyin: 用户输入的拼音。
        correct_word: 用户实际选择的词。
    """
    if not context.strip() or not pinyin.strip() or not correct_word.strip():
        return

    ctx_hash = _hash_context(context)
    _write_queue.put((ctx_hash, pinyin, correct_word, time.time()))


def _async_writer():
    """异步写入线程主循环，从队列读取纠错记录并批量写入数据库。"""
    global _writer_running
    _writer_running = True

    batch = []
    last_flush = time.time()

    while _writer_running:
        try:
            try:
                item = _write_queue.get(timeout=0.5)
                batch.append(item)
            except Exception:
                pass

            now = time.time()
            if batch and (len(batch) >= 10 or now - last_flush > 1.0):
                _flush_batch(batch)
                batch = []
                last_flush = now

        except Exception as e:
            get_logger().error(f"[记忆] 写入线程异常: {e}")

    if batch:
        _flush_batch(batch)


def _flush_batch(batch: list):
    """将批量纠错记录写入数据库（UPSERT 语义）。

    Args:
        batch: (context_hash, pinyin, correct_word, timestamp) 元组列表。
    """
    if not batch:
        return

    try:
        db = _get_db()
        for ctx_hash, pinyin, word, ts in batch:
            db.execute(
                """
                INSERT INTO corrections (context_hash, pinyin, correct_word, created_at, last_used, use_count)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(context_hash, pinyin, correct_word)
                DO UPDATE SET
                    last_used = excluded.last_used,
                    use_count = use_count + 1
                """,
                (ctx_hash, pinyin, word, ts, ts)
            )
        db.commit()
        get_logger().debug(f"[记忆] 写入 {len(batch)} 条纠错记录")
    except Exception as e:
        get_logger().error(f"[记忆] 批量写入异常: {e}")


def cleanup(max_age_days: int | None = None, max_records: int | None = None):
    """LRU 淘汰：清理过期和超量记录。

    先删除超过 max_age_days 天未使用的记录，
    再按 last_used 升序删除超出 max_records 的记录。

    Args:
        max_age_days: 最大保留天数，默认使用配置值。
        max_records: 最大记录数，默认使用配置值。
    """
    cfg = _get_memory_cfg()
    if max_age_days is None:
        max_age_days = cfg.max_age_days
    if max_records is None:
        max_records = cfg.max_records

    try:
        db = _get_db()

        cutoff = time.time() - max_age_days * 86400
        cursor = db.execute(
            "DELETE FROM corrections WHERE last_used < ?",
            (cutoff,)
        )
        deleted = cursor.rowcount

        cursor = db.execute("SELECT COUNT(*) FROM corrections")
        count = cursor.fetchone()[0]

        if count > max_records:
            excess = count - max_records
            db.execute(
                """
                DELETE FROM corrections
                WHERE id IN (
                    SELECT id FROM corrections
                    ORDER BY last_used ASC
                    LIMIT ?
                )
                """,
                (excess,)
            )
            deleted += excess

        db.commit()

        if deleted > 0:
            get_logger().info(f"[记忆] 清理完成: 删除 {deleted} 条记录")

    except Exception as e:
        get_logger().error(f"[记忆] 清理异常: {e}")


def get_stats() -> dict:
    """获取记忆库统计信息。

    Returns:
        包含 total_records 和 recent_24h 字段的字典。
    """
    try:
        db = _get_db()
        cursor = db.execute("SELECT COUNT(*) FROM corrections")
        total = cursor.fetchone()[0]

        cursor = db.execute(
            "SELECT COUNT(*) FROM corrections WHERE last_used > ?",
            (time.time() - 86400,)
        )
        recent = cursor.fetchone()[0]

        return {
            "total_records": total,
            "recent_24h": recent,
        }
    except Exception as e:
        get_logger().error(f"[记忆] 统计异常: {e}")
        return {"total_records": 0, "recent_24h": 0}


def init_memory():
    """初始化记忆模块：建表、启动异步写入线程、执行一次清理。"""
    global _writer_thread

    _init_db()

    _writer_thread = threading.Thread(
        target=_async_writer,
        daemon=True,
        name="memory-writer"
    )
    _writer_thread.start()

    cleanup()

    stats = get_stats()
    get_logger().info(f"[记忆] 初始化完成: {stats['total_records']} 条记录")


def shutdown_memory():
    """关闭记忆模块：停止写入线程并关闭数据库连接。"""
    global _writer_running
    _writer_running = False
    if _writer_thread:
        _writer_thread.join(timeout=2.0)

    if hasattr(_local, "db") and _local.db:
        _local.db.close()
        _local.db = None
