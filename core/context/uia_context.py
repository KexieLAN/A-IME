"""UIA 上下文抓取模块。

使用 Windows UIAutomation 接口获取当前焦点控件的光标前文本。
三级瀑布策略：
1. TextPattern 字符级回退法 (Word、WPS、记事本等)
2. ValuePattern (浏览器地址栏、VS Code 等纯文本输入框)
3. Name 属性保底 (部分非标控件将文字藏在 Name 属性中)
"""

import threading
import pythoncom
import uiautomation as auto
from config import get_config
from core.shutdown import is_shutdown, wait_shutdown

_cfg = get_config().context
auto.SetGlobalSearchTimeout(_cfg.uia_timeout)

GLOBAL_CONTEXT: str = ""
CONTEXT_LOCK = threading.Lock()


def uia_get_context() -> str:
    """使用 UIA 瀑布流策略提取当前焦点控件的光标前文本。

    按优先级依次尝试 TextPattern → ValuePattern → Name，
    任一策略成功即返回，全部失败返回空字符串。

    Returns:
        光标前文本，最多 max_chars 个字符，换行符替换为 ↵。
    """
    try:
        focused = auto.GetFocusedControl()
        if not focused:
            return ""

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
                        -_cfg.max_chars
                    )
                    raw_text = fetch_range.GetText(-1)
                    if raw_text and raw_text.strip():
                        text = raw_text[-_cfg.max_chars:] if len(raw_text) > _cfg.max_chars else raw_text
                        return text.replace('\r', '').replace('\n', ' ↵ ')
        except Exception:
            pass

        try:
            value_pattern = focused.GetValuePattern()
            if value_pattern:
                raw_text = value_pattern.Value
                if raw_text and raw_text.strip():
                    text = raw_text[-_cfg.max_chars:] if len(raw_text) > _cfg.max_chars else raw_text
                    return text.replace('\r', '').replace('\n', ' ↵ ')
        except Exception:
            pass

        try:
            if focused.Name and focused.Name.strip():
                text = focused.Name[-_cfg.max_chars:] if len(focused.Name) > _cfg.max_chars else focused.Name
                return text.replace('\r', '').replace('\n', ' ↵ ')
        except Exception:
            pass

        return ""
    except Exception:
        return ""


def context_watchdog_worker():
    """后台看门狗线程，以 poll_interval 间隔持续抓取上下文。

    使用 wait_shutdown 替代 time.sleep 以支持优雅退出。
    每轮抓取结果写入 GLOBAL_CONTEXT 并由 CONTEXT_LOCK 保护。
    """
    global GLOBAL_CONTEXT
    print("🐕 UIA 上下文看门狗已启动，跨应用文本探测挂载完毕...")
    pythoncom.CoInitialize()

    while not is_shutdown():
        try:
            context_text = uia_get_context()
            with CONTEXT_LOCK:
                GLOBAL_CONTEXT = context_text
        except Exception:
            with CONTEXT_LOCK:
                GLOBAL_CONTEXT = ""

        wait_shutdown(_cfg.poll_interval)
