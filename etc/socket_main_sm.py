import socket
import json
import threading
import win32com.client
import time
import ctypes

HOST = "127.0.0.1"
PORT = 5000
BUFFER_SIZE = 4096

lastest_version_id = ""

# ==========================================
# ⚙️ 全局状态区
# ==========================================
GLOBAL_CONTEXT = ""
CONTEXT_LOCK = threading.Lock()


# ==========================================
# 🚀 角色互换：TCP 引擎放入后台子线程
# ==========================================
def process_ai_logic(data):
    version_id = data.get("version_id")
    pinyin = data.get("pinyin", "")
    candidates = data.get("candidates", [])

    # 瞬间从内存中拿到主线程刚刚抓好的上下文
    with CONTEXT_LOCK:
        current_context = GLOBAL_CONTEXT

    reranked = [{"word": w, "score": 10.0 - i} for i, w in enumerate(reversed(candidates))]

    # 你可以在这里打印一下 current_context 看看效果
    # print(f"🧠 [AI使用上下文]: {current_context}")

    return {
        "version_id": version_id,
        "status": "success",
        "generated_word": f"🤖生成({pinyin})",
        "reranked_candidates": reranked
    }


def tcp_server_worker():
    global lastest_version_id

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(5)
        print(f"🚀 Context-IME TCP引擎已在后台线程启动！监听 {HOST}:{PORT}...")

        while True:
            try:
                conn, addr = server.accept()
                with conn:
                    raw_data = conn.recv(BUFFER_SIZE)
                    if not raw_data: continue

                    parts = raw_data.split(b"\r\n\r\n", 1)
                    if len(parts) < 2: continue

                    body = parts[1].decode("utf-8")
                    request_data = json.loads(body)

                    lastest_version_id = request_data.get("version_id", "")

                    start_time = time.time()
                    response_data = process_ai_logic(request_data)
                    calc_time = (time.time() - start_time) * 1000

                    print(f"\n⚡ [处理完毕] 耗时: {calc_time:.1f}ms | 拼音: {request_data.get('pinyin')}")

                    res_body = json.dumps(response_data, ensure_ascii=False)
                    res_payload = (
                        "HTTP/1.1 200 OK\r\n"
                        "Content-Type: application/json; charset=utf-8\r\n"
                        f"Content-Length: {len(res_body.encode('utf-8'))}\r\n"
                        "Connection: close\r\n\r\n"
                        f"{res_body}"
                    )
                    conn.sendall(res_payload.encode("utf-8"))
            except Exception as e:
                print(f"⚠️ TCP服务器异常: {e}")


# ==========================================
# 🕵️ 角色互换：看门狗霸占主线程 (带窗口嗅探器)
# ==========================================
def is_word_active():
    """使用 Win32 API 极速嗅探当前最前面的窗口是不是 Word"""
    user32 = ctypes.windll.user32
    # 瞬间获取当前活动窗口句柄
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False

    # 获取窗口类名
    class_name_buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_name_buffer, 256)

    # Word 的主窗口类名永远是 "OpusApp"
    return class_name_buffer.value == "OpusApp"


def start_watchdog_in_main_thread():
    global GLOBAL_CONTEXT
    print("🐕 主线程看门狗已启动，环境嗅探器挂载完毕...")

    while True:
        try:
            context_text = ""  # 默认设为空

            # 1. 嗅探当前窗口：只有当用户真正聚焦在 Word 时，才去抓取
            if is_word_active():
                word_app = win32com.client.GetActiveObject("Word.Application")
                selection = word_app.Selection

                if selection.Type == 1:
                    virtual_range = selection.Range
                    virtual_range.MoveStart(1, -50)

                    # 取出文本并清洗回车符
                    raw_text = virtual_range.Text
                    if raw_text:
                        context_text = str(raw_text).replace('\r', ' ↵ ')

            # 2. 统一更新全局变量
            # 如果不是 Word，或者发生了切屏，context_text 会是默认的 ""
            # 这就完美实现了“切出窗口立即清空上下文”的隔离效果！
            with CONTEXT_LOCK:
                GLOBAL_CONTEXT = context_text

        except Exception:
            # 发生任何异常（比如 Word 彻底关了），也立刻清空残留的上下文
            with CONTEXT_LOCK:
                GLOBAL_CONTEXT = ""

        # 巡逻间隔保持 0.5s
        time.sleep(0.5)
        print(f"当前上下文: '{GLOBAL_CONTEXT}'") # 取消注释可以观察切屏效果


if __name__ == '__main__':
    # 1. 把 TCP 服务器扔进后台线程 (Daemon 守护线程)
    tcp_thread = threading.Thread(target=tcp_server_worker, daemon=True)
    tcp_thread.start()

    # 2. 主线程亲自执行 UIA 看门狗死循环
    start_watchdog_in_main_thread()
