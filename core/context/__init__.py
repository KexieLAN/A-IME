"""UIA 上下文抓取模块。

使用 Windows UIAutomation 接口获取当前焦点控件的光标前文本，
支持三级瀑布策略：TextPattern → ValuePattern → Name。
"""

from .uia_context import uia_get_context, context_watchdog_worker
from . import uia_context

__all__ = ["uia_get_context", "context_watchdog_worker", "uia_context"]
