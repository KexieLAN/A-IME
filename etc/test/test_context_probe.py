import uiautomation as auto
import time
import pythoncom

auto.SetGlobalSearchTimeout(0.3)

ROUNDS = 10


def uia_get_context_old():
    t_start = time.perf_counter()
    result = {"text": "", "method": "none", "phases": {}}

    try:
        focused = auto.GetFocusedControl()
        t_focused = time.perf_counter()
        result["phases"]["get_focused"] = (t_focused - t_start) * 1000

        if not focused:
            result["phases"]["total"] = (time.perf_counter() - t_start) * 1000
            return result

        try:
            text_pattern = focused.GetTextPattern()
            if text_pattern:
                selections = text_pattern.GetSelection()
                t_sel = time.perf_counter()
                result["phases"]["get_selection"] = (t_sel - t_focused) * 1000

                if selections and len(selections) > 0:
                    cursor_range = selections[0]

                    para_range = cursor_range.Clone()
                    para_range.ExpandToEnclosingUnit(auto.TextUnit.Paragraph)

                    fetch_range = cursor_range.Clone()
                    fetch_range.MoveEndpointByRange(
                        auto.TextPatternRangeEndpoint.Start,
                        para_range,
                        auto.TextPatternRangeEndpoint.Start
                    )
                    t_range = time.perf_counter()
                    result["phases"]["range_ops"] = (t_range - t_sel) * 1000

                    raw_text = fetch_range.GetText(-1)
                    t_text = time.perf_counter()
                    result["phases"]["get_text"] = (t_text - t_range) * 1000

                    if raw_text and raw_text.strip():
                        text = raw_text[-150:] if len(raw_text) > 150 else raw_text
                        result["text"] = text.replace('\r', '').replace('\n', ' ↵ ')
                        result["method"] = "TextPattern-OLD"
                        result["phases"]["total"] = (time.perf_counter() - t_start) * 1000
                        return result
        except Exception as e:
            result["phases"]["textpattern_err"] = str(e)

        try:
            value_pattern = focused.GetValuePattern()
            if value_pattern:
                raw_text = value_pattern.Value
                if raw_text and raw_text.strip():
                    text = raw_text[-150:] if len(raw_text) > 150 else raw_text
                    result["text"] = text.replace('\r', '').replace('\n', ' ↵ ')
                    result["method"] = "ValuePattern"
                    result["phases"]["total"] = (time.perf_counter() - t_start) * 1000
                    return result
        except Exception:
            pass

    except Exception as e:
        result["phases"]["global_err"] = str(e)

    result["phases"]["total"] = (time.perf_counter() - t_start) * 1000
    return result


def uia_get_context_new():
    t_start = time.perf_counter()
    result = {"text": "", "method": "none", "phases": {}}

    try:
        focused = auto.GetFocusedControl()
        t_focused = time.perf_counter()
        result["phases"]["get_focused"] = (t_focused - t_start) * 1000

        if not focused:
            result["phases"]["total"] = (time.perf_counter() - t_start) * 1000
            return result

        try:
            text_pattern = focused.GetTextPattern()
            if text_pattern:
                selections = text_pattern.GetSelection()
                t_sel = time.perf_counter()
                result["phases"]["get_selection"] = (t_sel - t_focused) * 1000

                if selections and len(selections) > 0:
                    cursor_range = selections[0]
                    fetch_range = cursor_range.Clone()
                    fetch_range.MoveEndpointByUnit(
                        auto.TextPatternRangeEndpoint.Start,
                        auto.TextUnit.Character,
                        -150
                    )
                    t_range = time.perf_counter()
                    result["phases"]["range_ops"] = (t_range - t_sel) * 1000

                    raw_text = fetch_range.GetText(-1)
                    t_text = time.perf_counter()
                    result["phases"]["get_text"] = (t_text - t_range) * 1000

                    if raw_text and raw_text.strip():
                        text = raw_text[-150:] if len(raw_text) > 150 else raw_text
                        result["text"] = text.replace('\r', '').replace('\n', ' ↵ ')
                        result["method"] = "TextPattern-NEW"
                        result["phases"]["total"] = (time.perf_counter() - t_start) * 1000
                        return result
        except Exception as e:
            result["phases"]["textpattern_err"] = str(e)

        try:
            value_pattern = focused.GetValuePattern()
            if value_pattern:
                raw_text = value_pattern.Value
                if raw_text and raw_text.strip():
                    text = raw_text[-150:] if len(raw_text) > 150 else raw_text
                    result["text"] = text.replace('\r', '').replace('\n', ' ↵ ')
                    result["method"] = "ValuePattern"
                    result["phases"]["total"] = (time.perf_counter() - t_start) * 1000
                    return result
        except Exception:
            pass

    except Exception as e:
        result["phases"]["global_err"] = str(e)

    result["phases"]["total"] = (time.perf_counter() - t_start) * 1000
    return result


def run_ab_comparison():
    print("=" * 60)
    print("🔬 A/B 对比：旧方案 (ExpandToEnclosingUnit) vs 新方案 (MoveEndpointByUnit)")
    print("   请在 5 秒内聚焦到目标输入框 (Word / 浏览器 / 记事本...)")
    print("=" * 60)
    pythoncom.CoInitialize()

    for i in range(5, 0, -1):
        print(f"   ⏳ {i}...")
        time.sleep(1)

    print()
    print(f"  {'轮次':>4s} | {'旧方案':>12s} | {'新方案':>12s} | {'提速':>8s} | {'文本预览'}")
    print("  " + "-" * 90)

    old_totals = []
    new_totals = []

    for r in range(ROUNDS):
        old_result = uia_get_context_old()
        old_total = old_result["phases"].get("total", 0)
        old_range = old_result["phases"].get("range_ops", 0)

        new_result = uia_get_context_new()
        new_total = new_result["phases"].get("total", 0)
        new_range = new_result["phases"].get("range_ops", 0)

        old_totals.append(old_total)
        new_totals.append(new_total)

        speedup = old_total / new_total if new_total > 0 else float('inf')
        text_preview = new_result["text"][:30] if new_result["text"] else "[空]"

        print(f"  {r+1:4d} | {old_total:9.2f}ms | {new_total:9.2f}ms | {speedup:6.1f}x | {text_preview}")
        print(f"         └─ range_ops: 旧={old_range:.1f}ms → 新={new_range:.1f}ms")

        time.sleep(0.3)

    print()
    avg_old = sum(old_totals) / len(old_totals)
    avg_new = sum(new_totals) / len(new_totals)
    overall_speedup = avg_old / avg_new if avg_new > 0 else float('inf')
    print(f"  📊 平均耗时: 旧={avg_old:.1f}ms → 新={avg_new:.1f}ms | 整体提速 {overall_speedup:.1f}x")
    print()


def run_new_watchdog():
    print("=" * 60)
    print("🐕 新方案看门狗循环 (500ms 间隔)")
    print("   测量优化后连续轮询的实际刷新延迟，共 10 轮")
    print("   请保持焦点在目标输入框中，并在测试期间尝试打字")
    print("=" * 60)
    pythoncom.CoInitialize()

    time.sleep(3)

    prev_text = ""
    lag_events = []

    for r in range(10):
        t0 = time.perf_counter()
        result = uia_get_context_new()
        fetch_ms = (time.perf_counter() - t0) * 1000
        current_text = result["text"]

        text_changed = current_text != prev_text
        change_marker = "📝 变化!" if text_changed else "  ──"

        print(f"  轮 {r+1:2d} | 抓取={fetch_ms:6.1f}ms | {change_marker} | {current_text[:50] if current_text else '[空]'}")

        if fetch_ms > 200:
            lag_events.append((r + 1, fetch_ms, result["method"]))

        prev_text = current_text
        time.sleep(0.5)

    print()
    if lag_events:
        print("⚠️ 高延迟事件:")
        for idx, ms, method in lag_events:
            print(f"   轮 {idx}: {ms:.1f}ms (策略: {method})")
    else:
        print("✅ 所有轮次均在 200ms 内完成")


def run_new_distribution():
    print("=" * 60)
    print("📊 新方案延迟分布统计 (20 次采样)")
    print("=" * 60)
    pythoncom.CoInitialize()

    time.sleep(3)

    latencies = []
    methods = {}

    for r in range(20):
        result = uia_get_context_new()
        total = result["phases"].get("total", 0)
        method = result["method"]
        latencies.append(total)
        methods[method] = methods.get(method, 0) + 1
        time.sleep(0.3)

    latencies.sort()
    avg = sum(latencies) / len(latencies)
    p50 = latencies[len(latencies) // 2]
    p90 = latencies[int(len(latencies) * 0.9)]
    p99 = latencies[-1]
    mx = max(latencies)
    mn = min(latencies)

    print(f"  最小: {mn:.1f}ms")
    print(f"  平均: {avg:.1f}ms")
    print(f"  P50:  {p50:.1f}ms")
    print(f"  P90:  {p90:.1f}ms")
    print(f"  P99:  {p99:.1f}ms")
    print(f"  最大: {mx:.1f}ms")
    print()
    print(f"  策略命中分布: {methods}")

    slow_count = sum(1 for l in latencies if l > 100)
    print(f"  >100ms 次数: {slow_count}/{len(latencies)}")


if __name__ == "__main__":
    print("🚀 AIME 上下文抓取优化验证探针")
    print("   旧方案: ExpandToEnclosingUnit(Paragraph) → ~1000ms")
    print("   新方案: MoveEndpointByUnit(Character, -150) → 预计 ~1-5ms\n")

    run_ab_comparison()
    run_new_watchdog()
    run_new_distribution()

    print("\n" + "=" * 60)
    print("🏁 验证完成！请将以上结果发给我，我来确认优化效果。")
    print("=" * 60)
