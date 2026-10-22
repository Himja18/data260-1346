"""HW5 Part 5 - agent loop over the three s1346_rel tools.

run_agent(user_input) -> dict(answer, stop_reason, steps, tool_calls, run_id)

  * one model turn per step; a turn can request tool calls or give a final answer
  * every tool call goes through execute_tool (envelope + safety rule)
  * turn counter with a max_steps ceiling
  * every step, tool call, input, result and the final stop reason is appended
    to reports/hw05/raw/agent_runs.jsonl

Stop reasons: "completed"   - model gave a final answer
              "safety_block" - a tool call violated the safety rule
              "max_steps"   - step ceiling reached before an answer
              "model_error" - the model could not be reached / returned garbage

Models: OllamaModel (local, default qwen2.5:3b) and MockModel (scripted, offline).
"""
import json
import os
import re
import time
import uuid
from datetime import UTC, datetime

from domain_tools import SCHEMAS, execute_tool

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_LOG = os.path.join(ROOT, "reports", "hw05", "raw", "agent_runs.jsonl")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
SEED = 1346
DEFAULT_MAX_STEPS = 5

TOOL_DESCRIPTIONS = {
    "search_incidents": "Search transit incidents, newest first. Optional filters: category "
                        "(Delay|Breakdown|Accident|Service Change), line_code like 'L-005', "
                        "text in the route title. limit 1-50 (default 10).",
    "get_incident": "Full details for one incident by code, e.g. 'INC-000123'.",
    "incident_stats": "Incident count and passengers affected per category, for one line "
                      "('L-005') or all lines if line_code is omitted.",
}
TOOL_SPECS = [{"type": "function",
               "function": {"name": n, "description": TOOL_DESCRIPTIONS[n], "parameters": SCHEMAS[n]}}
              for n in SCHEMAS]

SYSTEM_PROMPT = (
    "You are a transit operations assistant for the s1346 Municipal Transit Incidents "
    "database. Use the provided tools to answer; never invent incident data. "
    "Line codes look like L-005 and incident codes like INC-005005. "
    "When you have enough information, answer briefly in plain text without calling a tool."
)


# ---- models -------------------------------------------------------------------
class OllamaModel:
    def __init__(self, model=MODEL_NAME, url=OLLAMA_URL, timeout=120):
        self.name, self.url, self.timeout = model, url, timeout

    def complete(self, messages, tools):
        import httpx
        r = httpx.post(self.url, timeout=self.timeout, json={
            "model": self.name, "messages": messages, "tools": tools, "stream": False,
            "options": {"temperature": 0, "seed": SEED},
        })
        r.raise_for_status()
        msg = r.json()["message"]
        calls = [{"name": c["function"]["name"], "arguments": c["function"].get("arguments") or {}}
                 for c in msg.get("tool_calls") or []]
        content = msg.get("content") or ""
        if not calls:                       # small models sometimes write the call as text
            calls = _calls_from_text(content)
            if calls:
                content = ""
        return {"content": content, "tool_calls": calls}


class MockModel:
    """Scripted model for offline tests. Each script item is either
    {"tool": name, "arguments": {...}} or {"answer": "..."}; the last item repeats."""
    name = "mock"

    def __init__(self, script):
        self.script, self.i = list(script), 0

    def complete(self, messages, tools):
        step = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        if "answer" in step:
            return {"content": step["answer"], "tool_calls": []}
        return {"content": "", "tool_calls": [{"name": step["tool"], "arguments": step.get("arguments", {})}]}


def _calls_from_text(text):
    for m in re.finditer(r"\{.*\}", text or "", re.S):
        try:
            obj = json.loads(m.group(0))
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("name") in SCHEMAS:
            args = obj.get("arguments") or obj.get("parameters") or {}
            return [{"name": obj["name"], "arguments": args}]
    return []


# ---- logging ------------------------------------------------------------------
class RunLog:
    def __init__(self, path, run_id, model_name, user_input):
        self.path, self.base = path, {"run_id": run_id, "model": model_name}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.write("start", user_input=user_input)

    def write(self, event, **fields):
        rec = {"ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
               **self.base, "event": event, **fields}
        with open(self.path, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")


def _short(envelope):
    """Keep the log readable: summarise big data payloads."""
    d = envelope.get("data")
    if isinstance(d, dict) and "results" in d:
        d = {"count": d.get("count"), "first": (d["results"] or [None])[0]}
    return {"ok": envelope.get("ok"), "data": d, "error": envelope.get("error")}


# ---- the loop -------------------------------------------------------------------
def run_agent(user_input, model=None, max_steps=DEFAULT_MAX_STEPS, repo=None,
              log_path=DEFAULT_LOG, run_id=None):
    model = model or OllamaModel()
    run_id = run_id or uuid.uuid4().hex[:8]
    log = RunLog(log_path, run_id, getattr(model, "name", "?"), user_input)
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input}]
    tool_calls, answer, stop_reason, step = 0, None, "max_steps", 0
    t0 = time.perf_counter()

    while step < max_steps:                                      # turn counter + ceiling
        step += 1
        try:
            reply = model.complete(messages, TOOL_SPECS)
        except Exception as e:                                   # noqa: BLE001
            stop_reason, answer = "model_error", f"model error: {e.__class__.__name__}: {e}"
            log.write("model_error", step=step, error=answer)
            break

        if not reply["tool_calls"]:                              # final answer
            answer, stop_reason = reply["content"].strip(), "completed"
            log.write("final_answer", step=step, answer=answer)
            break

        log.write("model_step", step=step, requested=[c["name"] for c in reply["tool_calls"]])
        messages.append({"role": "assistant", "content": reply["content"],
                         "tool_calls": [{"function": {"name": c["name"], "arguments": c["arguments"]}}
                                        for c in reply["tool_calls"]]})
        blocked = None
        for call in reply["tool_calls"]:
            tool_calls += 1
            raw = execute_tool(call["name"], call["arguments"], repo=repo)
            env = json.loads(raw)
            log.write("tool_call", step=step, tool=call["name"], input=call["arguments"],
                      result=_short(env))
            messages.append({"role": "tool", "tool_name": call["name"], "content": raw})
            if not env["ok"] and env["error"].startswith("blocked by safety rule"):
                blocked = env["error"]
                break
        if blocked:
            stop_reason = "safety_block"
            answer = f"I can't do that: {blocked}"
            break
    else:
        answer = f"Stopped after reaching the {max_steps}-step limit without a final answer."

    result = {"run_id": run_id, "answer": answer, "stop_reason": stop_reason,
              "steps": step, "tool_calls": tool_calls,
              "elapsed_s": round(time.perf_counter() - t0, 2)}
    log.write("stop", stop_reason=stop_reason, steps=step, tool_calls=tool_calls,
              elapsed_s=result["elapsed_s"], answer=answer)
    return result
