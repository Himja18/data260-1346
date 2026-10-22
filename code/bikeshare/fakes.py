"""Scripted chat model for offline tests of the LangGraph agent (no Ollama)."""
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedChatModel(BaseChatModel):
    """Returns scripted AIMessages in order; supports bind_tools like a real tool-calling model."""
    script: list
    i: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        """Tools are ignored - the script already knows which calls to make."""
        return self

    def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        step = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        if "tool" in step:
            msg = AIMessage(content="", tool_calls=[{"name": step["tool"], "args": step["args"],
                                                      "id": f"call_{self.i}", "type": "tool_call"}])
        else:
            msg = AIMessage(content=step["text"])
        return ChatResult(generations=[ChatGeneration(message=msg)])
