import win32com.client
import time


def test_word_native_api():
    print("🔍 Word 纯血 COM 内存直读探针启动！")
    print("👉 请在 3 秒内打开一个 Word，把光标随便放在一段文字的【中间】或【末尾】...")

    for i in range(3, 0, -1):
        print(f"⏳ {i}")
        time.sleep(1)

    print("\n⚡ 内存直读开始...")
    start_time = time.time()

    try:
        # 1. 瞬间劫持当前正在运行的 Word 进程句柄
        # 这不是操作 UI，这是直接与 Word 的 C++ 核心引擎对话！
        word_app = win32com.client.GetActiveObject("Word.Application")

        # 2. 获取当前的选中状态 (光标)
        selection = word_app.Selection

        # 确认光标是一个闪烁的点 (Type=1 代表 wdSelectionIP)，而不是选中了一大段字
        if selection.Type == 1:
            # 3. 核心魔法：在内存中克隆一个虚拟指针，绝对不会移动用户真实的 UI 光标
            virtual_range = selection.Range

            # 4. 把这个虚拟指针的起点向后(左)推 50 个字符
            # 1 代表 wdCharacter (按字符移动)
            virtual_range.MoveStart(1, -50)

            # 5. 直接从内存缓冲区 Dump 文本！
            context_text = virtual_range.Text

            calc_time = (time.time() - start_time) * 1000

            print("-" * 40)
            print(f"⏱️ COM 内存直读耗时: {calc_time:.2f} ms")

            # 清洗 Word 特有的段落标记 (Word 的回车符是 \r)
            display_text = str(context_text).replace('\r', ' ↵ ')
            print(f"📄 提取文本: {display_text}")
            print("-" * 40)

        else:
            print("⚠️ 请确保光标是一个闪烁的输入点，而不是选中了文字。")

    except Exception as e:
        print(f"❌ 劫持失败: {e}")
        print("💡 提示: 确保你的 Python 和 Word 权限一致 (比如不要一个用管理员运行，一个不用)。")


if __name__ == "__main__":
    test_word_native_api()