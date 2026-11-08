"""HW9 Part 4.2 - reusable lessons (lessons.json).

A lesson is created when the Evaluator Agent reports the SAME failure pattern for `min_repeats` failed
first answers (default 2 = a repeated pattern). Before answering, the Answering Agent loads the lessons
relevant to the question (trigger keywords; an empty list means "always relevant") and applies them;
use_count goes up each time a lesson is loaded.

Each lesson: lesson_id, failure_pattern, correction, created_at, use_count  (required)
             + pattern, trigger_keywords, action, status (candidate|kept|rejected), source, validation
"""
import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

TEMPLATES = {
    "stale_value": {
        "failure_pattern": "The answer gives the value from the first dispatch report instead of the current "
                           "verified value.",
        "correction": "For questions about the current status, delay, passenger count or category of an incident, "
                      "check the reference dataset (latest verified values) and state that value, not the "
                      "first-report value.",
        "trigger_keywords": ["current", "now", "latest", "still", "so far", "status", "delay", "passengers",
                             "passenger", "category", "classified"],
        "action": "consult_reference"},
    "missing_value": {
        "failure_pattern": "The answer does not state the specific value that was asked for.",
        "correction": "Start the answer with the exact value asked for (status, number of minutes or passengers, "
                      "category, line, location or required phone number).",
        "trigger_keywords": [],
        "action": None},
    "unsupported_answer": {
        "failure_pattern": "The answer gives details for an incident or topic that is not in the data.",
        "correction": "If the incident code is not in the data, or the question is not about transit incidents, "
                      "reply that there is no record in the s1346 incident data and give no details.",
        "trigger_keywords": [],
        "action": None},
    "unnecessary_decline": {
        "failure_pattern": "The answer says there is no record although the incident is in the data.",
        "correction": "If the incident code appears in the data, answer from that record instead of declining.",
        "trigger_keywords": [],
        "action": None},
}


class LessonStore:
    """lessons.json on disk + failure-pattern counter."""

    def __init__(self, path: Path, min_repeats: int = 2, frozen: bool = False) -> None:
        self.path = Path(path)
        self.min_repeats = min_repeats
        self.frozen = frozen                       # test runs: lessons are read, never written
        self.lessons: list[dict] = json.loads(self.path.read_text()) if self.path.exists() else []
        self.failures: dict[str, list[str]] = {}

    def save(self) -> None:
        """Write lessons.json (not when frozen)."""
        if not self.frozen:
            self.path.write_text(json.dumps(self.lessons, indent=2, ensure_ascii=False), encoding="utf-8")

    def reset(self) -> None:
        """Start with no lessons."""
        self.lessons, self.failures = [], {}
        self.save()

    def by_pattern(self, pattern: str) -> Optional[dict]:
        """Existing lesson for a failure pattern."""
        return next((x for x in self.lessons if x["pattern"] == pattern), None)

    def record_failure(self, pattern: Optional[str], question_id: str, dataset: str) -> Optional[dict]:
        """Count a failed first answer; create a lesson when the pattern repeats. Returns the new lesson."""
        if not pattern or self.frozen:
            return None
        self.failures.setdefault(pattern, []).append(question_id)
        if self.by_pattern(pattern) or len(self.failures[pattern]) < self.min_repeats:
            return None
        t = TEMPLATES[pattern]
        lesson = {"lesson_id": f"lesson_{len(self.lessons) + 1:03d}", "failure_pattern": t["failure_pattern"],
                  "correction": t["correction"], "created_at": date.today().isoformat(), "use_count": 0,
                  "pattern": pattern, "trigger_keywords": t["trigger_keywords"], "action": t["action"],
                  "status": "candidate",
                  "source": {"dataset": dataset, "failed_question_ids": list(self.failures[pattern])}}
        self.lessons.append(lesson)
        self.save()
        return lesson

    @staticmethod
    def is_relevant(lesson: dict, question: str) -> bool:
        """Trigger keyword in the question (no keywords = applies to every question)."""
        q = question.lower()
        kws = lesson.get("trigger_keywords") or []
        return not kws or any(re.search(r"\b" + re.escape(k) + r"\b", q) for k in kws)

    def relevant(self, question: str, statuses: tuple[str, ...]) -> list[dict]:
        """Lessons with an allowed status that apply to this question."""
        return [x for x in self.lessons if x["status"] in statuses and self.is_relevant(x, question)]

    def mark_used(self, lessons: list[dict]) -> None:
        """use_count += 1 for each loaded lesson."""
        if self.frozen or not lessons:
            return
        ids = {x["lesson_id"] for x in lessons}
        for x in self.lessons:
            if x["lesson_id"] in ids:
                x["use_count"] += 1
        self.save()

    def set_status(self, lesson_id: str, status: str, validation: dict) -> None:
        """kept / rejected after the validation check."""
        for x in self.lessons:
            if x["lesson_id"] == lesson_id:
                x["status"] = status
                x["validation"] = validation
        self.save()
