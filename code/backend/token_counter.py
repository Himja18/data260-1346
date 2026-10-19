"""HW6 Part 3: token counting for memory components.

Ollama only reports one prompt_eval_count per call, so the per-component
breakdown (primer / summaries / window / episodic facts) is counted with the
model's own tokenizer (Qwen2.5 from Hugging Face). If the tokenizer cannot be
loaded, a chars/4 heuristic is used and the method is recorded in every row.

Why we also count the full prompt ourselves: Ollama reuses its KV cache for an
unchanged prompt prefix, and prompt_eval_count then only counts the tokens it
actually had to evaluate. A hosted API bills the whole prompt, so the cost
estimate uses the tokenizer count of the full templated prompt.
"""
import logging
import math
from typing import Optional

from hw06_config import TOKENIZER_NAME

log = logging.getLogger("s1346.tokens")

_tokenizer = None
_method: Optional[str] = None


def _load() -> None:
    """Load the tokenizer once; fall back to the heuristic on any failure."""
    global _tokenizer, _method
    if _method is not None:
        return
    if TOKENIZER_NAME.lower() != "none":
        try:
            from transformers import AutoTokenizer
            _tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)
            _method = f"hf:{TOKENIZER_NAME}"
            return
        except Exception as exc:                       # noqa: BLE001 - optional dependency
            log.warning("tokenizer %s unavailable (%s); using chars/4", TOKENIZER_NAME, exc)
    _tokenizer = None
    _method = "heuristic:chars/4"


def method() -> str:
    """Name of the counting method actually in use."""
    _load()
    return _method or "unknown"


def count_tokens(text: str) -> int:
    """Tokens in a plain text block (no chat template)."""
    if not text:
        return 0
    _load()
    if _tokenizer is not None:
        return len(_tokenizer.encode(text, add_special_tokens=False))
    return math.ceil(len(text) / 4)


def count_chat_tokens(messages: list) -> int:
    """Tokens of the full prompt after the chat template is applied (what a hosted API bills)."""
    _load()
    if _tokenizer is not None:
        out = _tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        # newer transformers return a BatchEncoding/dict ({input_ids, attention_mask}), older a list
        ids = out["input_ids"] if hasattr(out, "keys") else out
        if ids and isinstance(ids[0], list):          # batched shape [[...]]
            ids = ids[0]
        return len(ids)
    # heuristic: content + ~4 template tokens per message + 3 for the generation prompt
    return sum(count_tokens(m["content"]) + 4 for m in messages) + 3
