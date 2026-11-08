"""HW9 Part 4 - Answering Agent (qwen2.5:3b through src/model_client.py).

By default the agent reads the dispatch feed (dispatch_snapshot.json): the FIRST report of each incident,
the lines and the reporting policies. Values such as status, delay and passenger count change after the
first report, so questions about the current value can fail. It can be told (by evaluator feedback on a
revision, or by a loaded lesson with action "consult_reference") to use the reference dataset's latest
verified values.
"""
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

INCIDENT_CODE = re.compile(r"\bINC-\d{6}\b", re.IGNORECASE)

SYSTEM = ("You are the Answering Agent of the s1346 Municipal Transit Incidents help desk. Answer the rider's "
          "question in 1-3 short sentences using ONLY the data provided. Incident categories are exactly Delay, "
          "Breakdown, Accident and Service Change. Plain text only.")


class AnsweringAgent:
    """Builds the prompt (data + lessons + feedback) and calls the model."""

    def __init__(self, model: Any, snapshot_path: Path, reference_path: Path) -> None:
        self.model = model
        self.snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
        self.reference = json.loads(Path(reference_path).read_text(encoding="utf-8"))
        self.snap_incidents = {i["incident_code"]: i for i in self.snapshot["incidents"]}
        self.ref_incidents = {i["incident_code"]: i for i in self.reference["incidents"]}

    def context(self, question: str, lessons: list[dict]) -> str:
        """Data block for this question."""
        codes = [c.upper() for c in INCIDENT_CODE.findall(question)]
        parts = []
        if codes:
            parts.append("Dispatch feed (first report of each incident):")
            for c in codes:
                rec = self.snap_incidents.get(c)
                parts.append(f"- {c}: no record in the dispatch feed" if rec is None else "- " + "; ".join(
                    f"{k}={v}" for k, v in rec.items()))
        elif "report" in question.lower():
            parts.append("Reporting policies:")
            parts += [f"- {p['topic']}: {p['text']}" for p in self.snapshot["policies"]]
        else:
            parts.append("Data: no dispatch record or policy matches this question.")
        if codes and any(x.get("action") == "consult_reference" for x in lessons):
            parts.append(f"Reference dataset - latest verified values (as of {self.reference['as_of']}):")
            for c in codes:
                r = self.ref_incidents.get(c)
                parts.append(f"- {c}: no record in the reference dataset" if r is None else
                             f"- {c}: category={r['category']}; current_status={r['current_status']}; "
                             f"current_delay_min={r['current_delay_min']}; "
                             f"passengers_affected={r['passengers_affected']}")
        return "\n".join(parts)

    def answer(self, question: str, lessons: list[dict], previous: Optional[str] = None,
               feedback: Optional[str] = None) -> dict:
        """One attempt. Returns {answer, prompt, ms}."""
        user = f"Question: {question}\n\n{self.context(question, lessons)}"
        if lessons:
            user += "\n\nLessons from earlier evaluations (apply them):\n" + "\n".join(
                f"- [{x['lesson_id']}] {x['correction']}" for x in lessons)
        if feedback:
            user += (f"\n\nYour previous answer: {previous}\nEvaluator feedback: {feedback}\n"
                     "Write a corrected answer that fixes exactly this problem.")
        t0 = time.perf_counter()
        reply = self.model.complete([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
        return {"answer": reply.content.strip(), "prompt": user, "ms": round((time.perf_counter() - t0) * 1000, 1)}


def make_model(fake: bool = False) -> Any:
    """ModelClient (qwen2.5:3b, temperature 0, seed 1346) or the offline fake."""
    if fake:
        return FakeModel()
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root / "src"))
    from model_client import ModelClient
    return ModelClient(model="qwen2.5:3b", temperature=0.0, seed=1346, num_predict=160, timeout_s=180)


class FakeModel:
    """Offline tests: 'answers' by copying the most recent data it was given (first report unless told otherwise)."""

    class _R:
        def __init__(self, content: str) -> None:
            self.content = content

    def complete(self, messages: list) -> "FakeModel._R":
        """Deterministic stand-in for the model."""
        user = messages[-1]["content"]
        if "Evaluator feedback:" in user:
            return self._R(user.split("Evaluator feedback:")[1].split("The reference dataset")[-1][:300])
        if "latest verified values" in user:
            return self._R(user.split("latest verified values")[1][:300])
        if "no record" in user or "no dispatch record" in user:
            return self._R("Here is what I think: it is probably fine.")
        return self._R(user.split("\n\n", 1)[1][:400])
