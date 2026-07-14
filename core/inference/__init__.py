"""两阶段推理引擎模块。

Phase 1 (选择策略)：从原生候选词中选出最符合语境的词。
Phase 2 (生成策略)：无中生有，突破本地词库天花板。
集成 L1 Cache 记忆体系和基于 logprobs 的候选词重排。
"""

import os
import time
from llama_cpp import Llama
from config import get_config
from core.logger import log_model, log_inference, log_error
from ..pinyin import pinyin_is_close, extract_chinese, get_pinyin, clean_context
from ..context import uia_context
from .. import memory

_cfg = get_config()
llm: Llama | None = None


def init_model():
    """加载 Qwen2.5-1.5B-Instruct Q4_K_M 到 GPU 显存。

    Raises:
        FileNotFoundError: 模型文件不存在时抛出。
    """
    global llm

    model_path = _cfg.model.path
    log_model(f"开始加载模型: {model_path}")

    if not os.path.exists(model_path):
        msg = f"找不到模型文件: {model_path}，请确保路径正确！"
        log_error(msg)
        raise FileNotFoundError(msg)

    t0 = time.time()
    llm = Llama(
        model_path=model_path,
        n_gpu_layers=_cfg.model.n_gpu_layers,
        logits_all=False,
        n_ctx=_cfg.model.n_ctx,
        verbose=False
    )
    elapsed = (time.time() - t0) * 1000
    log_model(f"模型加载完毕 ({elapsed:.0f}ms)，引擎处于待命状态！")


def phase1_selection(pinyin: str, candidates: list, short_context: str) -> str | None:
    """Phase 1 选择策略：从原生候选词中选出最符合语境的词。

    将候选词前 N 个作为"选择题"提交给模型，模型选出最合适的词。
    若选出的词与原生首位不同，返回该词；否则返回 None。

    Args:
        pinyin: 用户输入的拼音。
        candidates: 原生候选词列表。
        short_context: 光标前短上下文。

    Returns:
        选中的候选词，若原生首位已正确则返回 None。
    """
    if not candidates:
        return None

    inf_cfg = _cfg.inference

    try:
        native_list = ", ".join(candidates[:inf_cfg.max_candidates])

        messages = [
            {"role": "user",
             "content": f"前文：{short_context}\n"
                        f"拼音：{pinyin}\n"
                        f"候选：{native_list}\n"
                        f"最合适的词："}
        ]

        res = llm.create_chat_completion(
            messages=messages,
            stop=inf_cfg.stop_tokens,
            max_tokens=inf_cfg.max_tokens,
            temperature=inf_cfg.temperature
        )

        raw = res["choices"][0]["message"]["content"].strip()
        ai_pick = extract_chinese(raw.split('\n')[0])

        if ai_pick:
            if ai_pick in candidates:
                if ai_pick != candidates[0]:
                    pick_pinyin = get_pinyin(ai_pick)
                    print(f"✨ [Phase1 选择] {ai_pick} | 候选拼音: '{pick_pinyin}'")
                    return ai_pick
                else:
                    print(f"💤 [Phase1] 原生首位已正确 ({candidates[0]})")
            else:
                for c in candidates:
                    if c and ai_pick in c:
                        print(f"✨ [Phase1 模糊匹配] {c} (AI猜: {ai_pick})")
                        return c

    except Exception as e:
        log_error(f"Phase1 异常: {e}")

    return None


def phase2_generation(pinyin: str, candidates: list, short_context: str) -> str | None:
    """Phase 2 生成策略：从上下文和拼音直接生成候选词。

    仅在 Phase 1 未命中且拼音长度 ≥ phase2_min_pinyin_len 时触发。
    生成结果必须通过拼音碰撞验证（pinyin_is_close）。

    Args:
        pinyin: 用户输入的拼音。
        candidates: 原生候选词列表。
        short_context: 光标前短上下文。

    Returns:
        生成的候选词，验证失败返回 None。
    """
    inf_cfg = _cfg.inference

    if len(pinyin) < inf_cfg.phase2_min_pinyin_len:
        return None

    try:
        messages = [
            {"role": "user",
             "content": f"前文：{short_context}\n"
                        f"拼音：{pinyin}\n"
                        f"生成一个中文词："}
        ]

        res = llm.create_chat_completion(
            messages=messages,
            stop=inf_cfg.stop_tokens,
            max_tokens=inf_cfg.max_tokens,
            temperature=inf_cfg.temperature
        )

        raw = res["choices"][0]["message"]["content"].strip()
        ai_word = extract_chinese(raw.split('\n')[0])

        if ai_word and 1 <= len(ai_word) <= inf_cfg.max_generated_word_len:
            word_pinyin = get_pinyin(ai_word)

            if pinyin_is_close(pinyin, word_pinyin, inf_cfg.pinyin_threshold):
                len_wp = len(word_pinyin)
                generated_word = ai_word

                if len(pinyin) > len_wp + 2 and candidates:
                    top = candidates[0]
                    n = len(ai_word)
                    generated_word = ai_word + top[n:] if len(top) > n else ai_word

                if candidates and generated_word in candidates[:1]:
                    return None

                print(f"✨ [Phase2 生成] {generated_word} | 原始: '{ai_word}'")
                return generated_word
            else:
                print(f"💤 [Phase2 拼音不匹配] AI: '{ai_word}'('{word_pinyin}') vs 输入: '{pinyin}'")

    except Exception as e:
        log_error(f"Phase2 异常: {e}")

    return None


def rerank_candidates(pinyin: str, candidates: list, short_context: str) -> list[dict]:
    """使用模型 logprobs 对候选词进行真实打分重排。

    单次前向传播获取 top-20 token 概率，将候选词首字映射到
    对应的 logprob 作为置信度分数，按分数降序排列。

    Args:
        pinyin: 用户输入的拼音。
        candidates: 原生候选词列表。
        short_context: 光标前短上下文。

    Returns:
        重排后的候选词列表，每项包含 word 和 score 字段。
    """
    if len(candidates) <= 1:
        return [{"word": w, "score": 10.0 - i} for i, w in enumerate(candidates)]

    inf_cfg = _cfg.inference
    native_list = ", ".join(candidates[:inf_cfg.max_candidates])

    messages = [
        {"role": "user",
         "content": f"前文：{short_context}\n"
                    f"拼音：{pinyin}\n"
                    f"候选：{native_list}\n"
                    f"最合适的词："}
    ]

    try:
        res = llm.create_chat_completion(
            messages=messages,
            max_tokens=1,
            logprobs=True,
            top_logprobs=20,
            temperature=inf_cfg.temperature
        )

        logprobs_content = res["choices"][0].get("logprobs", {}).get("content", [])
        if not logprobs_content:
            return [{"word": w, "score": 10.0 - i} for i, w in enumerate(candidates)]

        top_logprobs = logprobs_content[0].get("top_logprobs", [])

        token_scores = {}
        for item in top_logprobs:
            token_scores[item["token"]] = item["logprob"]

        scored = []
        for i, candidate in enumerate(candidates):
            first_char = candidate[0] if candidate else ""
            score = token_scores.get(first_char, -100.0 - i)
            scored.append({"word": candidate, "score": round(score, 4)})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    except Exception as e:
        log_error(f"Rerank 异常: {e}")
        return [{"word": w, "score": 10.0 - i} for i, w in enumerate(candidates)]


def process_ai_logic(data: dict) -> dict:
    """AI 推理逻辑主函数。

    执行流程：读取上下文 → L1 Cache 查询 → Phase1 选择 →
    Phase2 生成 → 候选词重排 → 计算 covered_length → 返回结果。

    Args:
        data: 请求数据字典，包含 version_id、pinyin、candidates 等字段。

    Returns:
        响应数据字典，包含 version_id、status、generated_word、
        covered_length、reranked_candidates 字段。
    """
    version_id = data.get("version_id")
    pinyin_raw = data.get("pinyin", "")
    pinyin = pinyin_raw.replace('v', 'u')

    candidates = data.get("candidates", [])
    reranked = [{"word": w, "score": 10.0 - i} for i, w in enumerate(candidates)]

    with uia_context.CONTEXT_LOCK:
        current_context = uia_context.GLOBAL_CONTEXT

    if not current_context.strip():
        return {
            "version_id": version_id,
            "status": "success",
            "generated_word": None,
            "reranked_candidates": reranked
        }

    generated_word = None
    cleaned_context = clean_context(current_context)

    if not cleaned_context.strip() or len(pinyin) < 2:
        return {
            "version_id": version_id,
            "status": "success",
            "generated_word": None,
            "reranked_candidates": reranked
        }

    inf_cfg = _cfg.inference
    short_context = cleaned_context[-inf_cfg.short_context_chars:]

    t0 = time.time()

    cached_word = memory.query(short_context, pinyin)
    if cached_word and cached_word in candidates:
        elapsed = (time.time() - t0) * 1000
        log_inference(pinyin, elapsed, phase="L1", word=cached_word)
        print(f"🧠 [L1 记忆命中] {cached_word}")

        if cached_word != candidates[0]:
            covered_length = len(get_pinyin(cached_word))
            return {
                "version_id": version_id,
                "status": "success",
                "generated_word": cached_word,
                "covered_length": covered_length,
                "reranked_candidates": reranked
            }

    generated_word = phase1_selection(pinyin, candidates, short_context)

    if generated_word is None:
        generated_word = phase2_generation(pinyin, candidates, short_context)

    reranked = rerank_candidates(pinyin, candidates, short_context)

    elapsed = (time.time() - t0) * 1000

    covered_length = 0
    if generated_word:
        covered_length = len(get_pinyin(generated_word))

    log_inference(pinyin, elapsed, word=generated_word or "")

    return {
        "version_id": version_id,
        "status": "success",
        "generated_word": generated_word,
        "covered_length": covered_length,
        "reranked_candidates": reranked
    }
