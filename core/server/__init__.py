"""TCP 服务器模块。

提供本地 TCP Socket 服务，处理来自 RIME Lua 前端的请求。
支持两种请求类型：AI 推理请求（rerank）和纠错记录请求（correction）。
通过 socket.settimeout() 实现可被退出信号中断的事件循环。
"""

import socket
import json
import time
from config import get_config
from core.shutdown import is_shutdown
from core.logger import get_logger, log_warning
from ..inference import process_ai_logic
from ..context import uia_context
from .. import memory

_cfg = get_config().server


def _handle_correction(data: dict):
    """处理纠错记录请求。

    Lua 端不传 context 时自动使用当前 UIA 上下文。

    Args:
        data: 请求数据，包含 pinyin、correct_word，可选 context。
    """
    try:
        pinyin = data.get("pinyin", "")
        correct_word = data.get("correct_word", "")

        if not pinyin or not correct_word:
            return

        context = data.get("context", "")
        if not context:
            with uia_context.CONTEXT_LOCK:
                context = uia_context.GLOBAL_CONTEXT

        if context:
            memory.record_correction(context, pinyin, correct_word)
            get_logger().info(f"[纠错] 记录: {pinyin} -> {correct_word}")
    except Exception as e:
        log_warning(f"纠错记录异常: {e}")


def start_tcp_server():
    """启动 TCP 服务器，阻塞监听直到收到退出信号。

    接收 HTTP POST 请求，根据 type 字段分发到推理或纠错处理。
    通过 1 秒超时的 accept() 轮询 is_shutdown() 标志实现可退出循环。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((_cfg.host, _cfg.port))
        server.listen(5)
        server.settimeout(1.0)

        print(f"🚀 AIME 极速引擎已启动！监听 {_cfg.host}:{_cfg.port}...")
        get_logger().info(f"TCP 服务器启动 {_cfg.host}:{_cfg.port}")

        while not is_shutdown():
            try:
                conn, addr = server.accept()
            except socket.timeout:
                continue

            with conn:
                try:
                    raw_data = conn.recv(_cfg.buffer_size)
                    if not raw_data:
                        continue

                    parts = raw_data.split(b"\r\n\r\n", 1)
                    if len(parts) < 2:
                        continue

                    body = parts[1].decode("utf-8")
                    request_data = json.loads(body)

                    request_type = request_data.get("type", "rerank")

                    if request_type == "correction":
                        _handle_correction(request_data)
                        response_data = {"status": "ok"}
                    else:
                        start_time = time.time()
                        response_data = process_ai_logic(request_data)
                        calc_time = (time.time() - start_time) * 1000

                        print(f"\n{'='*60}")
                        print(f"⚡ [处理完毕] 耗时: {calc_time:.1f}ms | 拼音: {request_data.get('pinyin')}")
                        print(f"📝 [上下文] {uia_context.GLOBAL_CONTEXT[:80]}")
                        print(f"   => 原生候选: {request_data.get('candidates')}")
                        print(f"   => AI 生成:  {response_data.get('generated_word')}")
                        print(f"{'='*60}")

                    res_body = json.dumps(response_data, ensure_ascii=False)
                    res_payload = (
                        "HTTP/1.1 200 OK\r\n"
                        "Content-Type: application/json; charset=utf-8\r\n"
                        f"Content-Length: {len(res_body.encode('utf-8'))}\r\n"
                        "Connection: close\r\n\r\n"
                        f"{res_body}"
                    )
                    conn.sendall(res_payload.encode("utf-8"))

                except json.JSONDecodeError:
                    log_warning("JSON 解析失败")
                except ConnectionResetError:
                    log_warning("客户端连接重置")
                except Exception as e:
                    log_warning(f"请求处理异常: {e}")

        get_logger().info("TCP 服务器已停止")
