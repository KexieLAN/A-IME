import uiautomation as auto
import time

auto.SetGlobalSearchTimeout(0.1)


def test_uia_profiling():
    print("🔍 UIA 性能切片诊断探针启动！")
    print("👉 请在 3 秒内聚焦到 Word 输入框...")

    for i in range(3, 0, -1):
        print(f"⏳ {i}")
        time.sleep(1)

    print("\n⚡ 瞬间抓取开始...")

    # 记录总起点
    t0 = time.time()

    try:
        # [阶段 1：寻找焦点]
        focused_control = auto.GetFocusedControl()
        t1 = time.time()

        if not focused_control:
            print("❌ 未找到聚焦控件")
            return

        # [阶段 2：获取 TextPattern 并请求光标]
        text_pattern = focused_control.GetTextPattern()
        selections = text_pattern.GetSelection() if text_pattern else None
        t2 = time.time()

        # [阶段 3：段落扩展与文本提取]
        context_text = ""
        if selections and len(selections) > 0:
            cursor_range = selections[0]  # 当前绝对精确的光标位置 (长度为0)

            # 1. 建立参照物：克隆一个范围，并扩展到整个段落
            para_range = cursor_range.Clone()
            para_range.ExpandToEnclosingUnit(auto.TextUnit.Paragraph)

            # 2. 建立截取框：再克隆一个光标范围
            fetch_range = cursor_range.Clone()

            # 3. 核心魔法 (指针拉伸)：
            # 将 fetch_range 的【起点】，对齐到 para_range 的【起点】
            # 这在底层只是内存指针的赋值，耗时 0.0001ms，绝对不会引发 Word 排版计算！
            fetch_range.MoveEndpointByRange(
                auto.TextPatternRangeEndpoint.Start,
                para_range,
                auto.TextPatternRangeEndpoint.Start
            )

            # 4. 极速提取！此时拿到的正是“光标之前、段落之内”的精确文本
            text_before_cursor = fetch_range.GetText(-1)

            # 5. 在 Python 内存中进行切片保底 (只要最后 50 个字)
            context_text = text_before_cursor[-50:] if len(text_before_cursor) > 50 else text_before_cursor
            fetch_method = "TextPattern (指针拉伸法)"
        t3 = time.time()

        # --- 打印诊断报告 ---
        print("-" * 40)
        print("📊 耗时诊断报告：")
        print(f"1. 寻找焦点 (GetFocusedControl): {(t1 - t0) * 1000:.2f} ms")
        print(f"2. 建立接口与光标定位:         {(t2 - t1) * 1000:.2f} ms")
        print(f"3. 文本截取与传输 (GetText):   {(t3 - t2) * 1000:.2f} ms")
        print(f"⭐ 总计耗时:                   {(t3 - t0) * 1000:.2f} ms")
        print("-" * 40)

        display_text = str(context_text).replace('\r', '').replace('\n', ' ↵ ')
        print(f"📄 提取文本: {display_text}")

    except Exception as e:
        print(f"❌ 异常: {e}")


def test_uia_context_fetch():
    print("🔍 UIA 上下文探测探针 (V2) 已启动！")
    print("👉 请在 3 秒内将鼠标点击并聚焦到任意输入框 (如记事本, Word, 浏览器)...")

    for i in range(3, 0, -1):
        print(f"⏳ 倒计时: {i}")
        time.sleep(1)

    print("\n⚡ 瞬间抓取开始...")
    start_time = time.time()

    try:
        # 获取当前焦点控件
        focused_control = auto.GetFocusedControl()
        if not focused_control:
            print("❌ 抓取失败：未找到任何聚焦的控件。")
            return

        print(f"✅ 捕获控件类型: {focused_control.ControlTypeName}")
        print(f"✅ 捕获控件类名: {focused_control.ClassName}")

        context_text = ""
        fetch_method = "未获取到有效文本"

        # ==========================================
        # 瀑布流探测逻辑：直接调用，靠异常来判断是否支持
        # ==========================================

        # 尝试 1: TextPattern (适用于 Word、高级富文本编辑器)
        try:
            text_pattern = focused_control.GetTextPattern()
            if text_pattern:
                selections = text_pattern.GetSelection()
                if selections and len(selections) > 0:
                    cursor_range = selections[0]  # 当前绝对精确的光标位置 (长度为0)

                    # 1. 建立参照物：克隆一个范围，并扩展到整个段落
                    para_range = cursor_range.Clone()
                    para_range.ExpandToEnclosingUnit(auto.TextUnit.Paragraph)

                    # 2. 建立截取框：再克隆一个光标范围
                    fetch_range = cursor_range.Clone()

                    # 3. 核心魔法 (指针拉伸)：
                    # 将 fetch_range 的【起点】，对齐到 para_range 的【起点】
                    # 这在底层只是内存指针的赋值，耗时 0.0001ms，绝对不会引发 Word 排版计算！
                    fetch_range.MoveEndpointByRange(
                        auto.TextPatternRangeEndpoint.Start,
                        para_range,
                        auto.TextPatternRangeEndpoint.Start
                    )

                    # 4. 极速提取！此时拿到的正是“光标之前、段落之内”的精确文本
                    text_before_cursor = fetch_range.GetText(-1)

                    # 5. 在 Python 内存中进行切片保底 (只要最后 50 个字)
                    context_text = text_before_cursor[-50:] if len(text_before_cursor) > 50 else text_before_cursor
                    fetch_method = "TextPattern (指针拉伸法)"
        except Exception:
            pass  # 不支持该接口，静默跳过

        # 尝试 2: ValuePattern (适用于记事本、浏览器地址栏、普通输入框)
        if not context_text or fetch_method == "未获取到有效文本":
            try:
                value_pattern = focused_control.GetValuePattern()
                if value_pattern:
                    context_text = value_pattern.Value
                    fetch_method = "ValuePattern (纯文本简单模式)"
            except Exception:
                pass

        # 尝试 3: Name 属性保底 (部分非标控件把文字藏在 Name 里)
        if not context_text or fetch_method == "未获取到有效文本":
            if focused_control.Name:
                context_text = focused_control.Name
                fetch_method = "Name Attribute (降级保底模式)"

        # ==========================================

        fetch_time = (time.time() - start_time) * 1000

        print("-" * 50)
        print(f"⏱️ 抓取耗时: {fetch_time:.2f} ms")
        print(f"📡 命中接口: {fetch_method}")

        # 清洗换行符以方便终端显示
        display_text = str(context_text).replace('\r', '').replace('\n', ' ↵ ')
        if not display_text.strip():
            display_text = "[获取到的内容为空]"

        print(f"📄 文本内容摘要:")
        print(f"👉 {display_text[:150]} ...")
        print("-" * 50)

    except Exception as e:
        print(f"❌ 抓取发生极其严重的异常: {e}")


if __name__ == "__main__":
    test_uia_profiling()

# import uiautomation as auto
# import time
#
# # 核心优化：将 UIA 的全局搜索超时强制压缩到最低！
# auto.SetGlobalSearchTimeout(0.5)
#
#
# def test_uia_profiling():
#     print("🔍 UIA 性能切片诊断探针启动！")
#     print("👉 请在 3 秒内聚焦到 Word 输入框...")
#
#     for i in range(3, 0, -1):
#         print(f"⏳ {i}")
#         time.sleep(1)
#
#     print("\n⚡ 瞬间抓取开始...")
#
#     # 记录总起点
#     t0 = time.time()
#
#     try:
#         # [阶段 1：寻找焦点]
#         focused_control = auto.GetFocusedControl()
#         t1 = time.time()
#
#         if not focused_control:
#             print("❌ 未找到聚焦控件")
#             return
#
#         # [阶段 2：获取 TextPattern 并请求光标]
#         text_pattern = focused_control.GetTextPattern()
#         selections = text_pattern.GetSelection() if text_pattern else None
#         t2 = time.time()
#
#         # [阶段 3：段落扩展与文本提取]
#         context_text = ""
#         if selections and len(selections) > 0:
#             cursor_range = selections[0]
#             cursor_range.ExpandToEnclosingUnit(auto.TextUnit.Paragraph)
#             para_text = cursor_range.GetText(-1)
#             context_text = para_text[-50:] if len(para_text) > 50 else para_text
#         t3 = time.time()
#
#         # --- 打印诊断报告 ---
#         print("-" * 40)
#         print("📊 耗时诊断报告：")
#         print(f"1. 寻找焦点 (GetFocusedControl): {(t1 - t0) * 1000:.2f} ms")
#         print(f"2. 建立接口与光标定位:         {(t2 - t1) * 1000:.2f} ms")
#         print(f"3. 文本截取与传输 (GetText):   {(t3 - t2) * 1000:.2f} ms")
#         print(f"⭐ 总计耗时:                   {(t3 - t0) * 1000:.2f} ms")
#         print("-" * 40)
#
#         display_text = str(context_text).replace('\r', '').replace('\n', ' ↵ ')
#         print(f"📄 提取文本: {display_text}")
#
#     except Exception as e:
#         print(f"❌ 异常: {e}")
#
#
# if __name__ == "__main__":
#     test_uia_profiling()
