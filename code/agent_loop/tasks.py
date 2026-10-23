"""HW7 Part 2/3 - the three fixed verification tasks and their deterministic verifiers.

Each task needs at least two tool calls. Ground truth is computed directly from the
database (repository queries, no model) at verification time, so the checks follow
whatever data is in s1346_rel instead of hard-coded answers.

verify(task, result, repo) -> Verdict(passed, checks, reason)
    strict, objective checks: required tool chain present in the trace, the right
    incident codes / counts appear in the answer, nothing contradicts the ground truth.
lenient_verify(...)  a looser re-check (accepts e.g. "4979" for "INC-004979" or
    "five hundred one") used ONLY to flag possible verifier false rejections for
    manual review in Part 3.
unsupported_claims(answer, result) -> claims in the answer that no tool observation backs.
"""
import json
import re
from dataclasses import dataclass, field
from typing import Any

INC_RE = re.compile(r"\bINC-\d{6}\b")
NUM_RE = re.compile(r"(?<![\w-])\d{1,3}(?:,\d{3})+(?![\w-])|(?<![\w-])\d+(?![\w-])")


@dataclass(frozen=True)
class Task:
    """One fixed verification case."""
    task_id: str
    kind: str
    prompt: str
    required_tools: tuple[str, ...]
    params: dict = field(default_factory=dict)


TASKS: list[Task] = [
    Task("A", "search -> detail lookup",
         "Search for incidents whose route title mentions 'Airport'. Then look up the full "
         "details of the first (newest) result and tell me its incident code, its category "
         "and the name of its transit line.",
         ("search_incidents", "get_incident"), {"text": "Airport"}),
    Task("B", "aggregate -> supporting example",
         "Show the incident counts per category for line L-033. Then find one supporting example "
         "of the most common category on that line and give its incident code and route title.",
         ("incident_stats", "search_incidents"), {"line_code": "L-033"}),
    Task("C", "compare: search + two detail lookups",
         "Compare the two most recent Breakdown incidents on line L-033: search for them, "
         "look up the details of each one, and tell me both incident codes, where each "
         "breakdown happened, and which one was reported more recently.",
         ("search_incidents", "get_incident"), {"category": "Breakdown", "line_code": "L-033"}),
]
TASKS_BY_ID = {t.task_id: t for t in TASKS}

ERROR_RECOVERY_PROMPT = ("Give me the full details of incident INC-999999 "
                         "(if it does not exist, say so and suggest what I can do instead).")


@dataclass
class Verdict:
    """Deterministic verifier result."""
    passed: bool
    checks: dict
    reason: str


def ground_truth(task: Task, repo: Any) -> dict:
    """Expected facts for one task, read straight from the database."""
    if task.task_id == "A":
        first = repo.search_incidents(None, None, task.params["text"], 1)[0]
        detail = repo.get_incident(first["incident_code"])
        return {"code": first["incident_code"], "category": detail["category"],
                "line_name": detail.get("line_name"), "line_code": detail.get("line_code")}
    if task.task_id == "B":
        stats = {r["category"]: r["incidents"] for r in repo.category_stats(task.params["line_code"])}
        top = max(stats.values()) if stats else 0
        return {"line": task.params["line_code"], "count": top,
                "top": sorted(k for k, v in stats.items() if v == top)}
    if task.task_id == "C":
        rows = repo.search_incidents("Breakdown", task.params["line_code"], None, 2)
        places = [r["route_title"].split(" near ")[-1].split(" at ")[-1] for r in rows]
        return {"codes": [r["incident_code"] for r in rows], "newest": rows[0]["incident_code"],
                "places": places}
    raise KeyError(task.task_id)


def _calls(result: Any, tool: str) -> list[dict]:
    return [t for t in result.tool_trace if t["tool"] == tool and t["ok"]]


def _numbers(text: str) -> set[int]:
    return {int(n.replace(",", "")) for n in NUM_RE.findall(text or "")}


def verify(task: Task, result: Any, repo: Any) -> Verdict:
    """Strict deterministic check of one run (trace + answer vs ground truth)."""
    gt = ground_truth(task, repo)
    ans = result.answer or ""
    codes = set(INC_RE.findall(ans))
    c: dict[str, bool] = {"final_answer": result.stop_reason == "final_answer"}
    if task.task_id == "A":
        c["searched_text"] = any((t["input"].get("text") or "").lower() == "airport"
                                 for t in _calls(result, "search_incidents"))
        c["looked_up_first_result"] = any(t["input"].get("incident_code") == gt["code"]
                                          for t in _calls(result, "get_incident"))
        c["answer_has_code"] = gt["code"] in codes
        c["answer_has_category"] = gt["category"].lower() in ans.lower()
        c["answer_has_line"] = bool(gt["line_name"]) and (gt["line_name"].lower() in ans.lower()
                                                          or gt["line_code"] in ans)
    elif task.task_id == "B":
        c["stats_for_line"] = any(t["input"].get("line_code") == gt["line"]
                                  for t in _calls(result, "incident_stats"))
        c["searched_for_example"] = bool(_calls(result, "search_incidents"))
        c["answer_has_top_count"] = gt["count"] in _numbers(ans)
        example_ok = False
        for code in codes:
            row = repo.get_incident(code)
            example_ok = example_ok or (row is not None and row["category"] in gt["top"]
                                        and row.get("line_code") == gt["line"])
        c["example_is_top_category_on_line"] = example_ok
    elif task.task_id == "C":
        c["searched_line"] = any(t["input"].get("line_code") == "L-033"
                                 for t in _calls(result, "search_incidents"))
        looked = {t["input"].get("incident_code") for t in _calls(result, "get_incident")}
        c["two_detail_lookups"] = set(gt["codes"]) <= looked
        c["answer_has_both_codes"] = set(gt["codes"]) <= codes
        c["answer_has_both_places"] = all(p.lower() in ans.lower() for p in gt["places"])
        newest = gt["newest"]
        sentences = re.split(r"(?<=[.!?])\s+", ans)
        c["names_newest"] = any(newest in s and re.search(r"recent|newer|latest|later", s, re.I)
                                for s in sentences)
    failed = [k for k, v in c.items() if not v]
    return Verdict(not failed, c, "all checks passed" if not failed else "failed: " + ", ".join(failed))


WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9, "ten": 10, "hundred": 100}


def lenient_verify(task: Task, result: Any, repo: Any) -> bool:
    """Looser answer check used only to flag possible false rejections for manual review."""
    gt = ground_truth(task, repo)
    ans = (result.answer or "").lower()
    bare = {str(int(c[4:])) for c in INC_RE.findall(result.answer or "")} | set(re.findall(r"\b\d{3,6}\b", ans))

    def has_code(code: str) -> bool:
        return code.lower() in ans or str(int(code[4:])) in bare

    if task.task_id == "A":
        return has_code(gt["code"]) and (gt["line_code"].lower() in ans
                                         or (gt["line_name"] or "").split(" - ")[-1].lower() in ans)
    if task.task_id == "B":
        nums = _numbers(ans)
        return gt["count"] in nums or f"{gt['count']:,}" in ans
    if task.task_id == "C":
        return all(has_code(code) for code in gt["codes"])
    return False


def unsupported_claims(result: Any, question: str = "") -> list[str]:
    """Incident codes and multi-digit numbers in the answer that no tool result contains."""
    observed = " ".join(t["result"] for t in result.tool_trace) + " " + question
    obs_codes = set(INC_RE.findall(observed))
    obs_nums = _numbers(observed)
    for t in result.tool_trace:          # counts the model may legitimately add up
        try:
            data = json.loads(t["result"]).get("data") or {}
        except ValueError:
            continue
        if isinstance(data, dict) and "count" in data:
            obs_nums.add(int(data["count"]))
    claims = []
    ans = result.answer or ""
    for code in sorted(set(INC_RE.findall(ans)) - obs_codes):
        claims.append(code)
    for n in sorted(_numbers(INC_RE.sub(" ", ans))):
        if n >= 10 and n not in obs_nums and not (1900 <= n <= 2100):
            claims.append(str(n))
    return claims
