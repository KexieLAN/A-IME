import socket
import json
import threading
import time
import pythoncom
import uiautomation as auto
from llama_cpp import Llama, LogitsProcessorList
import numpy as np
import re
from pypinyin import lazy_pinyin
import os
import difflib

auto.SetGlobalSearchTimeout(0.3)

MODEL_PATH = r"F:\QWen\qwen2.5-1.5b-instruct-q4_k_m.gguf"  # 替换为你的实际模型路径
print(f"⏳ 正在将大模型加载至 4060Ti 显存，请稍候...")

if not os.path.exists(MODEL_PATH):
    print(f"❌ 找不到模型文件: {MODEL_PATH}，请确保路径正确！")
    exit(1)

llm = Llama(
    model_path=MODEL_PATH,
    n_gpu_layers=-1,
    logits_all=False,
    n_ctx=1024*32,
    verbose=False  # 关闭 C++ 底层刷屏日志
)

print("✅ 模型加载完毕，引擎处于待命状态！")

HOST = "127.0.0.1"
PORT = 5000
BUFFER_SIZE = 4096

lastest_version_id = ""

# ==========================================
# ⚙️ 全局状态区
# ==========================================
# 这个变量就是我们的"L1 内存缓存"，永远存放着上一秒的光标上下文
GLOBAL_CONTEXT = ""
CONTEXT_LOCK = threading.Lock()


# ==========================================
# 🕵️ 后台看门狗线程 (只管静默抓取，慢点也无所谓)
# ==========================================
def uia_get_context():
    """使用 UIA 瀑布流策略提取当前焦点控件的光标前文本 (跨应用兼容)"""
    try:
        focused = auto.GetFocusedControl()
        if not focused:
            return ""

        # 策略 1: TextPattern 字符级回退法 (Word、WPS、记事本等)
        # 用 MoveEndpointByUnit(Character, -150) 替代 ExpandToEnclosingUnit(Paragraph)
        # 避免触发 Word 段落排版重算 (原 ~1000ms → 优化后 ~1-5ms)
        try:
            text_pattern = focused.GetTextPattern()
            if text_pattern:
                selections = text_pattern.GetSelection()
                if selections and len(selections) > 0:
                    cursor_range = selections[0]
                    fetch_range = cursor_range.Clone()
                    fetch_range.MoveEndpointByUnit(
                        auto.TextPatternRangeEndpoint.Start,
                        auto.TextUnit.Character,
                        -150
                    )
                    raw_text = fetch_range.GetText(-1)
                    if raw_text and raw_text.strip():
                        text = raw_text[-150:] if len(raw_text) > 150 else raw_text
                        return text.replace('\r', '').replace('\n', ' ↵ ')
        except Exception:
            pass

        # 策略 2: ValuePattern (浏览器地址栏、VS Code 等纯文本输入框)
        try:
            value_pattern = focused.GetValuePattern()
            if value_pattern:
                raw_text = value_pattern.Value
                if raw_text and raw_text.strip():
                    text = raw_text[-150:] if len(raw_text) > 150 else raw_text
                    return text.replace('\r', '').replace('\n', ' ↵ ')
        except Exception:
            pass

        # 策略 3: Name 属性保底 (部分非标控件将文字藏在 Name 属性中)
        try:
            if focused.Name and focused.Name.strip():
                text = focused.Name[-150:] if len(focused.Name) > 150 else focused.Name
                return text.replace('\r', '').replace('\n', ' ↵ ')
        except Exception:
            pass

        return ""
    except Exception:
        return ""


def context_watchdog_worker():
    global GLOBAL_CONTEXT
    print("🐕 UIA 上下文看门狗已启动，跨应用文本探测挂载完毕...")
    pythoncom.CoInitialize()

    while True:
        try:
            context_text = uia_get_context()
            with CONTEXT_LOCK:
                GLOBAL_CONTEXT = context_text
        except Exception:
            with CONTEXT_LOCK:
                GLOBAL_CONTEXT = ""

        time.sleep(0.5)


# ==========================================
# 🧠 两阶段推理引擎
# Phase 1: 选择策略 (Selection) — 从候选词中选最匹配的
# Phase 2: 生成策略 (Generation) — 无中生有，突破词库天花板
# ==========================================
def pinyin_is_close(user_pinyin, target_pinyin):
    if not user_pinyin or not target_pinyin:
        return False
    if user_pinyin == target_pinyin:
        return True
    if target_pinyin.startswith(user_pinyin):
        return True
    compare_len = min(len(user_pinyin), len(target_pinyin))
    if compare_len < 2:
        return False
    return difflib.SequenceMatcher(
        None, user_pinyin[:compare_len], target_pinyin[:compare_len]
    ).ratio() >= 0.60


def extract_chinese(text):
    return ''.join(re.findall(r'[\u4e00-\u9fa5]+', text))


def process_ai_logic(data):
    version_id = data.get("version_id")
    pinyin_raw = data.get("pinyin", "")
    pinyin = pinyin_raw.replace('v', 'u')

    candidates = data.get("candidates", [])
    reranked = [{"word": w, "score": 10.0 - i} for i, w in enumerate(candidates)]

    with CONTEXT_LOCK:
        current_context = GLOBAL_CONTEXT

    if not current_context.strip():
        return {
            "version_id": version_id,
            "status": "success",
            "generated_word": None,
            "reranked_candidates": reranked
        }

    generated_word = None
    clean_context = re.sub(r'[a-zA-Z\s]+$', '', current_context)

    if not clean_context.strip() or len(pinyin) < 2:
        return {
            "version_id": version_id,
            "status": "success",
            "generated_word": None,
            "reranked_candidates": reranked
        }

    short_context = clean_context[-100:]

    # ============================================================
    # Phase 1: 选择策略 (Selection)
    # 从原生候选词中选出最符合语境的词，天然解决拼音纠错问题
    # 对小模型而言 "选择题" 远比 "问答题" 可靠
    # ============================================================
    if candidates:
        try:
            native_list = ", ".join(candidates[:5])

            messages = [
                {"role": "system",
                 "content": "你是输入法选词助手。根据前文和拼音，从候选词中选出最合适的。只输出选中的词。"},
                {"role": "user",
                 "content": f"前文：{short_context}\n"
                            f"拼音：{pinyin}\n"
                            f"候选：{native_list}\n"
                            f"选："}
            ]

            res = llm.create_chat_completion(
                messages=messages,
                stop=["\n", "。", "，", "、"],
                max_tokens=6,
                temperature=0.0
            )

            raw = res["choices"][0]["message"]["content"].strip()
            ai_pick = extract_chinese(raw.split('\n')[0])

            if ai_pick:
                if ai_pick in candidates:
                    if ai_pick != candidates[0]:
                        generated_word = ai_pick
                        pick_pinyin = "".join(lazy_pinyin(ai_pick))
                        print(f"✨ [Phase1 选择] {ai_pick} | 输入: '{pinyin_raw}' | 候选拼音: '{pick_pinyin}'")
                    else:
                        print(f"💤 [Phase1] 原生首位已正确 ({candidates[0]})")
                else:
                    for c in candidates:
                        if c and ai_pick in c:
                            generated_word = c
                            print(f"✨ [Phase1 模糊匹配] {c} (AI猜: {ai_pick})")
                            break

        except Exception as e:
            print(f"⚠️ Phase1 异常: {e}")

    # ============================================================
    # Phase 2: 生成策略 (Generation)
    # 无中生有，突破本地词库天花板
    # 仅在 Phase1 未命中且拼音较长时触发，需通过拼音碰撞验证
    # ============================================================
    if generated_word is None and len(pinyin) >= 3:
        try:
            messages = [
                {"role": "system",
                 "content": "你是输入法。根据前文和拼音，输出一个最合适的中文词。只输出一个词。"},
                {"role": "user",
                 "content": f"前文：{short_context}\n拼音：{pinyin}\n词："}
            ]

            res = llm.create_chat_completion(
                messages=messages,
                stop=["\n", "。", "，", "、"],
                max_tokens=6,
                temperature=0.0
            )

            raw = res["choices"][0]["message"]["content"].strip()
            ai_word = extract_chinese(raw.split('\n')[0])

            if ai_word and 1 <= len(ai_word) <= 5:
                word_pinyin = "".join(lazy_pinyin(ai_word))

                if pinyin_is_close(pinyin, word_pinyin):
                    len_wp = len(word_pinyin)

                    if len(pinyin) > len_wp + 2 and candidates:
                        top = candidates[0]
                        n = len(ai_word)
                        generated_word = ai_word + top[n:] if len(top) > n else ai_word
                    else:
                        generated_word = ai_word

                    if candidates and generated_word in candidates[:1]:
                        generated_word = None
                    else:
                        print(f"✨ [Phase2 生成] {generated_word} | 输入: '{pinyin_raw}' | 原始: '{ai_word}'")
                else:
                    print(f"💤 [Phase2 拼音不匹配] AI: '{ai_word}'('{word_pinyin}') vs 输入: '{pinyin}'")

        except Exception as e:
            print(f"⚠️ Phase2 异常: {e}")

    covered_length = 0
    if generated_word:
        covered_length = len("".join(lazy_pinyin(generated_word)))

    return {
        "version_id": version_id,
        "status": "success",
        "generated_word": generated_word,
        "covered_length": covered_length,
        "reranked_candidates": reranked
    }


def start_tcp_server():
    global lastest_version_id

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(5)
        print(f"🚀 AIME 极速引擎已启动！监听 {HOST}:{PORT}...")

        while True:
            conn, addr = server.accept()
            with conn:
                try:
                    # 1. 极速接收数据
                    raw_data = conn.recv(BUFFER_SIZE)
                    if not raw_data:
                        continue

                    # 2. 暴力剥离 HTTP 头，提取 JSON 体
                    # Lua 发送的数据格式是 Header \r\n\r\n Body
                    parts = raw_data.split(b"\r\n\r\n", 1)
                    if len(parts) < 2:
                        continue

                    body = parts[1].decode("utf-8")
                    request_data = json.loads(body)

                    # 3. 提取版本号
                    current_version = request_data.get("version_id", "")
                    lastest_version_id = current_version

                    # ⚡ [并发防御优化]：如果在准备算分前，发现有更新的请求进来了，
                    # 理论上可以在这里直接 raise Exception 跳过计算，但本地同步阻塞模型下先走全量

                    # 4. 进入 AI 算分黑盒
                    start_time = time.time()
                    response_data = process_ai_logic(request_data)
                    calc_time = (time.time() - start_time) * 1000

                    # 5. 打印绝美的工作日志 (方便调试)
                    print(f"\n⚡ [处理完毕] 耗时: {calc_time:.1f}ms| 上下文: {GLOBAL_CONTEXT[-30:]} | 拼音: {request_data.get('pinyin')}")
                    print(f"   => 原生候选: {request_data.get('candidates')}")
                    print(f"   => AI 生成:  {response_data.get('generated_word')}")
                    print(f"   => AI 重排:  {response_data.get('reranked_candidates')}")

                    # 6. 将结果打包为 HTTP Response 砸回给 Lua (留作后续 Lua 接收用)
                    # 注意：当前 Lua 端我们写的是 tcp:close() 没有接收，
                    # 等 AI 逻辑写完，我们就去 Lua 端把接收代码补上！
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
                    print("❌ JSON 解析失败！")
                except Exception as e:
                    print(f"⚠️ 服务器异常: {e}")


if __name__ == '__main__':
    # 启动后台看门狗线程 (设置为守护线程，主程序退出它就退出)
    watchdog = threading.Thread(target=context_watchdog_worker, daemon=True)
    watchdog.start()

    start_tcp_server()
