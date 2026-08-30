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

from dataclasses import dataclass, field
from typing import Optional

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"


@dataclass
class CompletionResult:
    """Everything a caller needs from one complete() call."""
    content: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


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

    # Running totals across the life of this client instance
    cumulative_input_tokens: int = field(default=0, init=False)
    cumulative_output_tokens: int = field(default=0, init=False)
    turn_count: int = field(default=0, init=False)

    def complete(self, messages: list, tools: Optional[list] = None) -> CompletionResult:
        """
        Send a list of {"role": ..., "content": ...} messages to the model
        and return a CompletionResult with the response text and token
        counts for this turn. `tools` is accepted for interface-compatibility
        with tool-calling adapters but is not used by this local model.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature},
        }

        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()

        input_tokens = data.get("prompt_eval_count", 0)
        output_tokens = data.get("eval_count", 0)

        self.cumulative_input_tokens += input_tokens
        self.cumulative_output_tokens += output_tokens
        self.turn_count += 1

        return CompletionResult(
            content=data["message"]["content"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

    def stats(self) -> dict:
        """Return cumulative usage stats without altering any state."""
        return {
            "turn_count": self.turn_count,
            "cumulative_input_tokens": self.cumulative_input_tokens,
            "cumulative_output_tokens": self.cumulative_output_tokens,
            "cumulative_total_tokens": self.cumulative_input_tokens + self.cumulative_output_tokens,
        }