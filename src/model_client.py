"""
src/model_client.py — DATA-260 HW1 Part 4: Model Client and Token Accounting

A reusable model-adapter module defining a stable interface,
complete(messages, tools=None), that all model calls in this project go
through. Wraps a local Ollama model (qwen2.5:3b — see AI_USE.md for the
qwen3:8b -> qwen2.5:3b substitution rationale).

Token accounting:
Ollama's /api/chat response includes prompt_eval_count (input tokens) and
eval_count (output tokens) natively, so we don't need a separate tokenizer
library — we read these directly from the API response metadata.
"""

import os
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

OLLAMA_HOST = os.getenv("OLLAMA_HOST_URL", "http://localhost:11434")
OLLAMA_URL = f"{OLLAMA_HOST}/api/chat"
OLLAMA_EMBED_URL = f"{OLLAMA_HOST}/api/embed"
MODEL_NAME = "qwen2.5:3b"


@dataclass
class CompletionResult:
    """Everything a caller needs from one complete() call."""
    content: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: float = 0.0          # HW6: wall-clock time of this model call
    # HW7: native tool calls exactly as the model emitted them (arguments may be a
    # dict or a raw string - validation is the agent loop's job, not the adapter's).
    tool_calls: list = field(default_factory=list)


@dataclass
class ModelClient:
    """
    Stable adapter around the local Ollama model. All model calls in this
    project (hw1_client.py, agents_demo.py could also be pointed at this)
    should go through complete(), not call Ollama directly, so that token
    accounting stays centralized in one place.
    """
    model: str = MODEL_NAME
    temperature: float = 0.7
    seed: Optional[int] = None          # HW6: fixed seed for repeatable experiment runs
    num_predict: Optional[int] = None   # HW6: cap on output tokens (None = model default)
    timeout_s: float = 120.0

    # Running totals across the life of this client instance
    cumulative_input_tokens: int = field(default=0, init=False)
    cumulative_output_tokens: int = field(default=0, init=False)
    turn_count: int = field(default=0, init=False)

    def complete(self, messages: list, tools: Optional[list] = None,
                 options: Optional[dict] = None) -> CompletionResult:
        """
        Send a list of {"role": ..., "content": ...} messages to the model
        and return a CompletionResult with the response text and token
        counts for this turn. HW7: when `tools` (OpenAI-style function specs) is
        given it is sent to Ollama and any native tool calls are returned in
        CompletionResult.tool_calls as [{"name": str, "arguments": dict|str}].
        `options` (HW6) overrides Ollama options for this one call only.
        """
        opts = {"temperature": self.temperature}
        if self.seed is not None:
            opts["seed"] = self.seed
        if self.num_predict is not None:
            opts["num_predict"] = self.num_predict
        opts.update(options or {})
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": opts,
        }
        if tools:
            payload["tools"] = tools

        started = time.perf_counter()
        response = requests.post(OLLAMA_URL, json=payload, timeout=self.timeout_s)
        response.raise_for_status()
        data = response.json()

        input_tokens = data.get("prompt_eval_count", 0)
        output_tokens = data.get("eval_count", 0)

        self.cumulative_input_tokens += input_tokens
        self.cumulative_output_tokens += output_tokens
        self.turn_count += 1

        calls = [{"name": (c.get("function") or {}).get("name", ""),
                  "arguments": (c.get("function") or {}).get("arguments", {})}
                 for c in data["message"].get("tool_calls") or []]

        return CompletionResult(
            tool_calls=calls,
            content=data["message"].get("content") or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )

    def embed(self, texts: list, model: str = "nomic-embed-text") -> list:
        """HW6: embed texts with a local Ollama embedding model (optional backend)."""
        response = requests.post(OLLAMA_EMBED_URL, json={"model": model, "input": texts},
                                 timeout=self.timeout_s)
        response.raise_for_status()
        return response.json()["embeddings"]

    def stats(self) -> dict:
        """Return cumulative usage stats without altering any state."""
        return {
            "turn_count": self.turn_count,
            "cumulative_input_tokens": self.cumulative_input_tokens,
            "cumulative_output_tokens": self.cumulative_output_tokens,
            "cumulative_total_tokens": self.cumulative_input_tokens + self.cumulative_output_tokens,
        }
