"""Offline stand-ins for the HW1 ModelClient (tests and verify_hw07 - no Ollama needed)."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeResult:
    """Same fields the loop reads from model_client.CompletionResult."""
    content: str = ""
    tool_calls: list = field(default_factory=list)
    input_tokens: int = 50
    output_tokens: int = 10
    total_tokens: int = 60
    latency_ms: float = 1.0


class ScriptedClient:
    """Replays a fixed list of turns. Each item: {"tool": name, "arguments": ...} | {"text": str}
    | callable(messages) -> FakeResult. The last item repeats if the loop asks for more."""

    def __init__(self, script: list) -> None:
        self.script, self.i, self.seen = list(script), 0, []

    def complete(self, messages: list, tools: Any = None, options: Any = None) -> FakeResult:
        """Return the next scripted turn."""
        self.seen.append([dict(m) for m in messages])
        step = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        if callable(step):
            return step(messages)
        if "tool" in step:
            return FakeResult(tool_calls=[{"name": step["tool"], "arguments": step.get("arguments", {})}])
        return FakeResult(content=step["text"])
