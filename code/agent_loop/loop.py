"""HW7 Part 2 - the hand-written agent loop.

run_agent(user_input) -> AgentResult

  1. send the conversation + tool specs to the model through the HW1 adapter
     (src/model_client.py ModelClient.complete(messages, tools))
  2. if the model asked for tools: validate every call (known tool, JSON arguments,
     JSON-schema) -> execute it -> append the result as a role="tool" message
  3. if the model answered in text: that is the final answer
  4. repeat until a final answer or the hard iteration ceiling (MAX_ITERATIONS)

Repair path: an unknown tool, malformed arguments, a schema violation, or plain text
while required tool results are still missing is answered with ONE reprompt that names
the specific problem. Every repair uses one unit of a bounded repair budget
(MAX_REPAIRS); if the same opportunity fails again, or the budget is spent, the run
stops cleanly with stop_reason="repair_failed" (no exception, no crash).

Every tool invocation is logged (tool name + inputs + ok/error) to the "s1346.agent"
logger and to reports/hw07/raw/agent_runs.jsonl; the result reports total tool calls.
"""
import json
import logging
import re
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))       # code/
import hw07_config as cfg  # noqa: E402
from agent_loop.toolset import (  # noqa: E402
    LOST_CHAIN,
    MALFORMED_ARGS,
    TEXT_INSTEAD_OF_TOOL,
    CallCheck,
    SchemaToolset,
    domain_toolset,
)

log = logging.getLogger("s1346.agent")
if not log.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("    %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)
    log.propagate = False

DEFAULT_LOG = cfg.RAW_DIR / "agent_runs.jsonl"

SYSTEM_PROMPT = (
    "You are a transit operations assistant for the s1346 Municipal Transit Incidents "
    "database. You can only learn facts by calling the provided tools; never invent incident "
    "codes, counts or locations. Line codes look like L-005 and incident codes like INC-004979. "
    "For multi-step questions call one tool, read its result, then call the next tool. "
    "When every part of the question is answered from tool results, reply in plain text "
    "(no tool call) with a short answer that quotes the incident codes and numbers you used."
)


@dataclass
class Opportunity:
    """One model turn in which a tool call was needed, and how it ended."""
    turn: int
    first_try_ok: bool
    failure: str | None = None        # failure class of the first try
    repaired: bool = False            # a later valid call fixed it after the reprompt
    salvaged_from_text: bool = False  # a JSON tool call written as text was recovered


@dataclass
class AgentResult:
    """Everything a caller (reliability runner, Reflexion, UI) needs from one run."""
    run_id: str
    answer: str
    stop_reason: str                  # final_answer | max_iterations | repair_failed | budget_exhausted | model_error
    iterations: int
    tool_calls: int
    tool_trace: list = field(default_factory=list)      # [{tool, input, ok, error, result}]
    opportunities: list = field(default_factory=list)   # [Opportunity as dict]
    failures: list = field(default_factory=list)        # failure classes seen (first tries)
    repairs_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    chain_complete: bool = True

    @property
    def total_tokens(self) -> int:
        """Prompt + completion tokens over all model turns."""
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict:
        """JSON-friendly copy."""
        d = asdict(self)
        d["total_tokens"] = self.total_tokens
        return d


def _write(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def salvage_text_call(text: str, toolset: SchemaToolset) -> dict | None:
    """Small models sometimes write the tool call as JSON text; recover it if it names a real tool."""
    for m in re.finditer(r"\{.*\}", text or "", re.S):
        try:
            obj = json.loads(m.group(0))
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("name") in toolset.tools:
            return {"name": obj["name"], "arguments": obj.get("arguments", obj.get("parameters", {}))}
    return None


MODEL_VIEW_RESULTS = 10   # rows of a list result the MODEL sees; the full result stays in the trace


def model_view(raw: str) -> str:
    """Compact observation for a small model: long result lists are cut to MODEL_VIEW_RESULTS rows
    (HW7 fix after a real run where 50 rows made qwen2.5:3b summarise data instead of continuing)."""
    try:
        env = json.loads(raw)
    except ValueError:
        return raw
    data = env.get("data") if isinstance(env, dict) else None
    rows = data.get("results") if isinstance(data, dict) else None
    if isinstance(rows, list) and len(rows) > MODEL_VIEW_RESULTS:
        env["data"] = {**data, "results": rows[:MODEL_VIEW_RESULTS],
                       "note": f"showing {MODEL_VIEW_RESULTS} of {len(rows)} results"}
        return json.dumps(env, default=str)
    return raw


def _short(raw: str, limit: int = 400) -> str:
    return raw if len(raw) <= limit else raw[:limit] + f"... (+{len(raw) - limit} chars)"


def default_client() -> Any:
    """The HW1 model adapter with the HW7 agent settings."""
    from model_client import ModelClient
    return ModelClient(model=cfg.MODEL_NAME, temperature=cfg.AGENT_TEMPERATURE,
                       num_predict=cfg.AGENT_NUM_PREDICT)


def run_agent(user_input: str, client: Any = None, toolset: SchemaToolset | None = None,
              required_tools: list[str] | None = None, context_messages: list[dict] | None = None,
              system_prompt: str = SYSTEM_PROMPT, max_iterations: int = cfg.MAX_ITERATIONS,
              max_repairs: int = cfg.MAX_REPAIRS, tool_call_budget: int | None = None,
              token_budget: int | None = None, seed: int | None = None,
              log_path: Path | None = DEFAULT_LOG, run_id: str | None = None,
              tags: dict | None = None, require_success: bool = False) -> AgentResult:
    """Run the tool-calling loop until a final answer, a clean stop, or the iteration ceiling.

    require_success=True (Part 6 only): a required tool counts as done only after a SUCCESSFUL
    result, so a failed read_file (e.g. an invented path) triggers one reprompt instead of an answer.
    Default False keeps the Part 2/3 behaviour unchanged."""
    client = client or default_client()
    toolset = toolset or domain_toolset()
    required = list(required_tools or [])
    run_id = run_id or uuid.uuid4().hex[:8]
    res = AgentResult(run_id=run_id, answer="", stop_reason="max_iterations", iterations=0, tool_calls=0)
    messages = [{"role": "system", "content": system_prompt}, *(context_messages or []),
                {"role": "user", "content": user_input}]
    base = {"run_id": run_id, **(tags or {})}
    if log_path:
        _write(log_path, {"ts": cfg.now_iso(), **base, "event": "start", "input": user_input})
    log.info("[run %s] user: %s", run_id, user_input)
    pending: Opportunity | None = None       # opportunity waiting for its one repair
    pending_key: tuple = ()                  # (tool, failure class) that was just reprompted
    started = time.perf_counter()

    def fail_opportunity(opp: Opportunity, check_failure: str, message: str, reply: dict,
                         key: tuple = ()) -> bool:
        """Reprompt ONCE per specific problem. Stop (False) if the same problem comes back right after
        its reprompt, or the run's repair budget (max_repairs) is spent."""
        nonlocal pending_key
        if (pending is not None and key == pending_key) or res.repairs_used >= max_repairs:
            res.stop_reason = "repair_failed"
            res.answer = (f"Stopped: could not get a valid tool call after repair ({message}).")
            log.info("    repair failed -> stop: %s", message)
            return False
        res.repairs_used += 1
        pending_key = key
        messages.append(reply)
        messages.append({"role": "user", "content":
                         f"Your last response could not be executed: {message}. "
                         "Fix exactly this problem and respond again (call a tool with valid "
                         "arguments, or answer if you already have every tool result you need)."})
        log.info("    repair #%d (%s): %s", res.repairs_used, check_failure, message)
        return True

    while res.iterations < max_iterations:
        if tool_call_budget is not None and res.tool_calls >= tool_call_budget:
            res.stop_reason, res.answer = "budget_exhausted", res.answer or "Stopped: tool-call budget used up."
            break
        if token_budget is not None and res.total_tokens >= token_budget:
            res.stop_reason, res.answer = "budget_exhausted", res.answer or "Stopped: token budget used up."
            break
        res.iterations += 1
        try:
            kwargs = {"options": {"seed": seed}} if seed is not None else {}
            out = client.complete(messages, tools=toolset.specs, **kwargs)
        except Exception as exc:                                     # noqa: BLE001 - report, don't crash
            res.stop_reason, res.answer = "model_error", f"model error: {exc.__class__.__name__}: {exc}"
            log.info("    model error: %s", res.answer)
            break
        res.input_tokens += out.input_tokens
        res.output_tokens += out.output_tokens
        content = (out.content or "").strip()
        raw_calls = list(out.tool_calls or [])
        salvaged = False
        if not raw_calls and content:
            text_call = salvage_text_call(content, toolset)
            if text_call:
                raw_calls, salvaged = [text_call], True

        # A required tool counts as done once it has RUN - an error result (e.g. "not found")
        # is still a result the model may legitimately report (HW7 fix after the first real run).
        called_ok = {t["tool"] for t in res.tool_trace if t["ok"] or not require_success}
        missing = [t for t in required if t not in called_ok]

        # ---- plain text answer -------------------------------------------------------
        if not raw_calls:
            if missing:                     # text when a tool was still required
                # chain already started (some required tool ran) -> the model dropped the chain
                kind = LOST_CHAIN if any(t in called_ok for t in required) else TEXT_INSTEAD_OF_TOOL
                opp = pending or Opportunity(turn=res.iterations, first_try_ok=False, failure=kind)
                if pending is None:
                    res.opportunities.append(opp)
                    res.failures.append(kind)
                msg = (f"you answered in text but the task still needs tool results from: "
                       f"{', '.join(missing)}")
                if require_success and any(t["tool"] in missing and not t["ok"] for t in res.tool_trace):
                    msg += " (the last call failed - read its error and call the tool again with a corrected argument)"
                if not fail_opportunity(opp, kind, msg, {"role": "assistant", "content": content},
                                        key=("", kind)):
                    res.answer = content or res.answer
                    break
                pending = opp
                continue
            res.answer, res.stop_reason = content, "final_answer"
            break

        # ---- tool calls ----------------------------------------------------------------
        checks: list[tuple[dict, CallCheck]] = [(c, toolset.check(c)) for c in raw_calls]
        first_bad = [(c, ck) for c, ck in checks if not ck.ok]
        # Deterministic repair step: optional arguments sent as null/"" mean "not given" -> drop them
        # and re-validate before spending a reprompt (still counted as a malformed FIRST try).
        normalized = False
        for i, (c, ck) in enumerate(checks):
            args = c.get("arguments")
            if not ck.ok and ck.failure == MALFORMED_ARGS and isinstance(args, dict):
                cleaned = {k: v for k, v in args.items() if v not in (None, "")}
                if cleaned != args:
                    c2 = {**c, "arguments": cleaned}
                    ck2 = toolset.check(c2)
                    if ck2.ok:
                        log.info("    [normalized] %s: dropped empty optional args %s",
                                 c.get("name"), sorted(set(args) - set(cleaned)))
                        checks[i], normalized = (c2, ck2), True
        raw_calls = [c for c, _ in checks]
        bad = [(c, ck) for c, ck in checks if not ck.ok]
        if pending is None:
            opp = Opportunity(turn=res.iterations, first_try_ok=not first_bad and not salvaged,
                              failure=first_bad[0][1].failure if first_bad
                              else (TEXT_INSTEAD_OF_TOOL if salvaged else None),
                              salvaged_from_text=salvaged and not first_bad)
            res.opportunities.append(opp)
            if opp.failure:
                res.failures.append(opp.failure)
        else:
            opp = pending
        if all(isinstance(c.get("arguments") or {}, dict) for c in raw_calls):
            assistant_msg = {"role": "assistant", "content": "" if salvaged else content,
                             "tool_calls": [{"function": {"name": c.get("name", ""),
                                                          "arguments": c.get("arguments") or {}}}
                                            for c in raw_calls]}
        else:   # Ollama only accepts object arguments in history - echo a broken call as text
            assistant_msg = {"role": "assistant", "content": "Attempted tool call(s): " + json.dumps(
                [{"name": c.get("name"), "arguments": c.get("arguments")} for c in raw_calls], default=str)}
        if bad:
            call, ck = bad[0]
            log.info("    [invalid call] %s %s -> %s", call.get("name"), call.get("arguments"), ck.message)
            if log_path:
                _write(log_path, {"ts": cfg.now_iso(), **base, "event": "invalid_call",
                                  "iteration": res.iterations, "tool": call.get("name"),
                                  "input": call.get("arguments"), "failure": ck.failure,
                                  "message": ck.message})
            if not fail_opportunity(opp, ck.failure or "", ck.message, assistant_msg,
                                    key=(call.get("name"), ck.failure)):
                break
            pending = opp
            continue

        if pending is not None:
            pending.repaired = True
            pending, pending_key = None, ()
        if opp.salvaged_from_text or (normalized and not opp.first_try_ok):
            opp.repaired = True             # repair path without a reprompt (parsed / normalized)
        messages.append(assistant_msg)
        for call, ck in checks:
            res.tool_calls += 1
            raw = toolset.execute(call["name"], ck.arguments)
            try:
                env = json.loads(raw)
            except ValueError:
                env = {"ok": False, "error": "tool returned non-JSON"}
            ok = bool(env.get("ok", env.get("success", False)))
            err = env.get("error")
            log.info("    [tool %d] %s %s -> %s", res.tool_calls, call["name"],
                     json.dumps(ck.arguments), "ok" if ok else f"error: {err}")
            res.tool_trace.append({"iteration": res.iterations, "tool": call["name"],
                                   "input": ck.arguments, "ok": ok, "error": err, "result": raw})
            if log_path:
                _write(log_path, {"ts": cfg.now_iso(), **base, "event": "tool_call",
                                  "iteration": res.iterations, "tool": call["name"],
                                  "input": ck.arguments, "ok": ok, "error": err,
                                  "result": _short(raw)})
            messages.append({"role": "tool", "tool_name": call["name"], "content": model_view(raw)})
    else:
        res.answer = res.answer or f"Stopped after the {max_iterations}-iteration ceiling without a final answer."

    called_ok = {t["tool"] for t in res.tool_trace if t["ok"]}
    res.chain_complete = all(t in called_ok for t in required)
    if (res.stop_reason in ("final_answer", "max_iterations") and not res.chain_complete
            and LOST_CHAIN not in res.failures):
        res.failures.append(LOST_CHAIN)       # ran out of turns / answered with the chain unfinished
    res.latency_ms = round((time.perf_counter() - started) * 1000, 1)
    log.info("    stop=%s iterations=%d tool_calls=%d repairs=%d tokens=%d latency=%.0f ms",
             res.stop_reason, res.iterations, res.tool_calls, res.repairs_used,
             res.total_tokens, res.latency_ms)
    log.info("    answer: %s", (res.answer or "").replace("\n", " ")[:400])
    if log_path:
        _write(log_path, {"ts": cfg.now_iso(), **base, "event": "stop", "stop_reason": res.stop_reason,
                          "iterations": res.iterations, "tool_calls": res.tool_calls,
                          "repairs_used": res.repairs_used, "failures": res.failures,
                          "tokens": res.total_tokens, "latency_ms": res.latency_ms,
                          "answer": res.answer})
    return res
