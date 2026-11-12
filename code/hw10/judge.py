"""HW10 Parts 2-3 - GEval (DeepEval) judge on a local model, 1-5 scale, with a hard time bound.

Judge model: qwen2.5:3b served by the same local Ollama as the agents (documented in hw10_config):
temperature 0.3, no fixed seed, num_predict 256, JSON-schema constrained output, 120 s per call.

GEval scores on its own 0-10 rubric and returns score in [0, 1]. Every score in HW10 is reported on
1-5 as  score_1_5 = round(1 + 4 * geval_score)  (raw value kept as score_raw), so judge scores and the
human labels use the same 1-5 scale (1 = very poor, 5 = excellent).
Each metric is given fixed evaluation_steps, so GEval makes exactly one judge call per score.
"""
import concurrent.futures
import hashlib
import json
import os
import random
import time
from typing import Any, Optional

import requests

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_DISABLE_PROGRESS_BAR", "1")

import hw10_config as cfg  # noqa: E402

try:
    from deepeval.test_case import SingleTurnParams as Params  # deepeval >= 4
except ImportError:  # pragma: no cover
    from deepeval.test_case import LLMTestCaseParams as Params
from deepeval.metrics import GEval  # noqa: E402
from deepeval.models import DeepEvalBaseLLM  # noqa: E402
from deepeval.test_case import LLMTestCase  # noqa: E402

METRICS = {
    "plan_quality": {
        "name": "Plan Quality",
        "steps": [
            "Read the rider's question (input) and the Planner's plan (actual output, one step per line).",
            "Check that every step is specific to this question (route, incident, category or action) and is not "
            "a generic placeholder.",
            "Check that the steps together cover what a complete answer needs for this question: what the "
            "incident is or how to classify it, the value or action the rider asked for, and what happens next.",
            "Check that a Writer could follow the steps directly and that no step contradicts the records "
            "included in the question.",
            "Score high only if following the plan would produce a complete, correct answer; score low for vague, "
            "missing, wrong or off-topic steps.",
        ],
    },
    "writer_helpfulness": {
        "name": "Writer Helpfulness",
        "steps": [
            "Read the question (input), including any s1346_rel database records appended to it, and the "
            "Writer's draft (actual output).",
            "Accuracy: every number, category, line, location and date in the draft must match the records in "
            "the question; an invented or contradicting fact is a serious error.",
            "Usefulness: the draft must directly give the value or the concrete action the rider asked for.",
            "Penalize drafts that ask the rider for information instead of answering, answer a different "
            "question, or pad the answer with irrelevant text.",
            "Score high only for an accurate, direct and useful draft; score low for wrong, off-topic or "
            "unhelpful drafts.",
        ],
    },
    "final_helpfulness": {
        "name": "Final Answer Helpfulness",
        "steps": [
            "Read the rider's question (input) and the final answer delivered to the rider (actual output).",
            "Relevance: the answer must address this exact question.",
            "Helpfulness: after reading it, the rider must know the answer or exactly what to do next.",
            "Penalize answers that miss the asked value, contain off-topic content, contradict records in the "
            "question, or ask questions back instead of answering.",
            "Score high only when the answer is relevant, complete and clear.",
        ],
    },
}


class OllamaJudge(DeepEvalBaseLLM):
    """DeepEval custom model -> local Ollama /api/chat with JSON-schema output."""

    def __init__(self, model: str = cfg.JUDGE_MODEL) -> None:
        self.model_name = model
        super().__init__(model)

    def load_model(self) -> "OllamaJudge":
        """Nothing to load: Ollama holds the weights."""
        return self

    def _chat(self, prompt: str, fmt: Any) -> str:
        body = {"model": self.model_name, "stream": False, "format": fmt,
                "messages": [{"role": "user", "content": prompt}],
                "options": {"temperature": cfg.JUDGE_TEMPERATURE, "num_predict": cfg.JUDGE_NUM_PREDICT}}
        r = requests.post(f"{cfg.OLLAMA_URL}/api/chat", json=body, timeout=cfg.JUDGE_TIMEOUT_S)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def generate(self, prompt: str, schema: Any = None) -> Any:
        """Return a schema instance when DeepEval asks for one, else text."""
        if schema is None:
            return self._chat(prompt, "json")
        try:                                   # Ollama >= 0.5: constrain the reply to the schema
            return schema.model_validate_json(self._chat(prompt, schema.model_json_schema()))
        except Exception:  # noqa: BLE001 - older Ollama or a reply that does not validate: plain JSON mode once
            text = self._chat(prompt + "\nReply with JSON only.", "json")
            start, end = text.find("{"), text.rfind("}")
            return schema.model_validate_json(text[start:end + 1] if start != -1 else text)

    async def a_generate(self, prompt: str, schema: Any = None) -> Any:
        """Synchronous underneath (the evaluator runs one judge call at a time)."""
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        """Shown in DeepEval output."""
        return f"ollama/{self.model_name}"


class FakeJudge(DeepEvalBaseLLM):
    """Offline tests only: length/keyword heuristic plus a little noise."""

    def __init__(self) -> None:
        super().__init__("fake-judge")

    def load_model(self) -> "FakeJudge":
        """No model."""
        return self

    def generate(self, prompt: str, schema: Any = None) -> Any:
        """Deterministic-ish ReasonScore."""
        out = prompt.split("Actual Output", 1)[-1][:600].lower()
        base = 3 + (2 if any(c.isdigit() for c in out) else 0) - (2 if "could you" in out or "?" in out else 0)
        noise = random.Random(hashlib.md5(prompt.encode()).hexdigest() + str(time.time_ns() % 3)).choice([-1, 0, 0, 1])
        score = max(0, min(10, 2 * base + noise))
        data = {"reason": f"fake judge: base {base}", "score": score}
        return schema.model_validate(data) if schema is not None else json.dumps(data)

    async def a_generate(self, prompt: str, schema: Any = None) -> Any:
        """Same as generate."""
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        """Name."""
        return "fake-judge"


_JUDGE: Optional[DeepEvalBaseLLM] = None
_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="judge")


def judge_model() -> DeepEvalBaseLLM:
    """One judge model per process."""
    global _JUDGE
    if _JUDGE is None:
        _JUDGE = FakeJudge() if cfg.JUDGE_BACKEND == "fake" else OllamaJudge()
    return _JUDGE


def judge_settings() -> dict:
    """Documented settings, saved next to every result for reproducibility."""
    return {"framework": "DeepEval GEval", "judge_model": judge_model().get_model_name(),
            "temperature": cfg.JUDGE_TEMPERATURE, "seed": None, "num_predict": cfg.JUDGE_NUM_PREDICT,
            "timeout_s": cfg.JUDGE_TIMEOUT_S, "scale": "1-5 = round(1 + 4 * GEval score)",
            "evaluation_steps": "fixed per metric (one judge call per score)"}


def _measure(metric_key: str, question: str, output: str) -> tuple[float, str]:
    spec = METRICS[metric_key]
    metric = GEval(name=spec["name"], evaluation_steps=spec["steps"],
                   evaluation_params=[Params.INPUT, Params.ACTUAL_OUTPUT], model=judge_model(),
                   async_mode=False, verbose_mode=False)
    metric.measure(LLMTestCase(input=question, actual_output=output), _show_indicator=False)
    return float(metric.score), str(metric.reason or "")


def score(metric_key: str, question: str, output: str, timeout_s: float = cfg.JUDGE_TIMEOUT_S) -> dict:
    """One bounded judge call. Never raises and never waits longer than timeout_s (+ small slack)."""
    t0 = time.perf_counter()
    if not isinstance(output, str) or not output.strip():
        return {"metric": metric_key, "status": "error", "error": "empty or malformed output", "score": None,
                "score_raw": None, "geval_score": None, "reason": "", "ms": 0.0}
    fut = _POOL.submit(_measure, metric_key, question, output)
    try:
        g, reason = fut.result(timeout=timeout_s + 5)
        raw = cfg.SCORE_MIN + (cfg.SCORE_MAX - cfg.SCORE_MIN) * g
        return {"metric": metric_key, "status": "ok", "score": int(round(raw)), "score_raw": round(raw, 2),
                "geval_score": round(g, 3), "reason": reason, "error": None,
                "ms": round((time.perf_counter() - t0) * 1000, 1)}
    except concurrent.futures.TimeoutError:
        err = f"judge timeout after {timeout_s:.0f}s"
    except Exception as exc:  # noqa: BLE001 - unavailable judge, bad JSON, HTTP error ...
        err = f"{exc.__class__.__name__}: {str(exc)[:200]}"
    return {"metric": metric_key, "status": "error", "error": err, "score": None, "score_raw": None,
            "geval_score": None, "reason": "", "ms": round((time.perf_counter() - t0) * 1000, 1)}
