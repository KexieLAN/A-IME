"""拼音处理工具模块。

提供拼音转换、拼音碰撞验证、中文提取、上下文清洗等功能。
"""

import re
import difflib
from pypinyin import lazy_pinyin


def pinyin_is_close(user_pinyin: str, target_pinyin: str, threshold: float = 0.60) -> bool:
    """判断两个拼音是否相似（拼音碰撞验证）。

    依次检查：精确匹配 → 前缀匹配 → difflib 相似度 ≥ threshold。

    Args:
        user_pinyin: 用户输入的拼音。
        target_pinyin: 目标拼音。
        threshold: 相似度阈值，默认 0.60。

    Returns:
        两个拼音是否足够相似。
    """
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
    ).ratio() >= threshold


def extract_chinese(text: str) -> str:
    """从文本中提取连续中文字符。

    Args:
        text: 输入文本。

    Returns:
        提取的中文字符拼接结果，无中文时返回空字符串。
    """
    return ''.join(re.findall(r'[\u4e00-\u9fa5]+', text))


def get_pinyin(text: str) -> str:
    """获取中文文本的拼音字符串。

    Args:
        text: 中文文本。

    Returns:
        拼音字符串（无声调）。
    """
    return "".join(lazy_pinyin(text))


def clean_context(context: str) -> str:
    """清洗上下文文本，去除末尾英文单词和空白字符。

    Args:
        context: 原始上下文文本。

    Returns:
        清洗后的上下文文本。
    """
    return re.sub(r'[a-zA-Z\s]+$', '', context)
