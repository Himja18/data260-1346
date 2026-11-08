"""HW9 Part 4 - self-improving two-agent system (Answering Agent + Evaluator Agent).

    python code/hw09/part4/run_hw09_part4.py controlled   # 4.1 forced-incomplete first answer -> feedback -> revision
    python code/hw09/part4/run_hw09_part4.py train        # training_data: repair + lesson creation/reuse (4.2)
    python code/hw09/part4/run_hw09_part4.py validate     # 4.3 keep a lesson only if validation_data does not regress
    python code/hw09/part4/run_hw09_part4.py test         # 4.4 four variants on test_data (lessons frozen)
    python code/hw09/part4/run_hw09_part4.py all          # the four steps in order

Agent communication: the system passes plain JSON-able messages between the two agents -
  question -> Answering Agent -> {answer} -> Evaluator Agent -> {result, explanation, feedback}
  -> (REVISE) Answering Agent gets {previous answer, feedback} -> {answer} -> Evaluator Agent -> final.
Stopping condition: PASS, or the second attempt (max 2), whichever comes first.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

import hw09_config as cfg  # noqa: E402
from answering_agent import AnsweringAgent, make_model  # noqa: E402
from evaluator_agent import EvaluatorAgent  # noqa: E402
from hw09_common import banner, setup_logging, short, write_json  # noqa: E402
from lessons import LessonStore  # noqa: E402

DATA = cfg.PART4_DATA
REFERENCE = DATA / "reference_data.json"
SNAPSHOT = DATA / "dispatch_snapshot.json"
LESSONS = DATA / "lessons.json"

CONTROLLED_QUESTION = ("CT01", "What is the current status of incident INC-260101?")
CONTROLLED_BAD_FIRST = "Incident INC-260101 is a Breakdown on Line 22 at Fillmore St & Geary Blvd."   # omits the status

VARIANTS = {   # name -> (max attempts, lesson statuses loaded)
    "Baseline": (1, ()),
    "Evaluator Repair": (2, ()),
    "Lesson Memory": (2, ("candidate", "kept", "rejected")),   # every lesson saved in training, no gate
    "Validated Improvement": (2, ("kept",)),                   # only lessons that passed validation
}


def load_questions(name: str) -> list[tuple[str, str]]:
    """[(id, question)] from a dataset file (questions only - no expected answers)."""
    data = json.loads((DATA / name).read_text(encoding="utf-8"))
    return [(q["id"], q["question"]) for q in data["questions"]]


class TwoAgentSystem:
    """Runs one question through answer -> evaluate -> (revise -> evaluate)."""

    def __init__(self, answerer: AnsweringAgent, evaluator: EvaluatorAgent, log, store: LessonStore = None,  # noqa: ANN001
                 statuses: tuple = (), max_attempts: int = 2, learn: bool = False, dataset: str = "") -> None:
        self.answerer, self.evaluator, self.log = answerer, evaluator, log
        self.store, self.statuses, self.max_attempts = store, statuses, max_attempts
        self.learn, self.dataset = learn, dataset

    def run(self, qid: str, question: str, forced_first: str = None, quiet: bool = False) -> dict:  # noqa: RUF013
        """Returns the full record (attempts, final answer, final evaluation, latency)."""
        say = (lambda *a: None) if quiet else self.log.info
        t0 = time.perf_counter()
        lessons = self.store.relevant(question, self.statuses) if (self.store and self.statuses) else []
        say("[%s] QUESTION: %s", qid, question)
        if lessons:
            say("[%s] lessons loaded: %s", qid, ", ".join(f"{x['lesson_id']} ({x['pattern']}, used "
                                                          f"{x['use_count']}x before)" for x in lessons))
        attempts, previous, feedback = [], None, None
        for n in range(1, self.max_attempts + 1):
            if n == 1 and forced_first is not None:
                out = {"answer": forced_first, "ms": 0.0, "forced": True}
                say("[%s] attempt %d (CONTROLLED: intentionally incomplete): %s", qid, n, forced_first)
            else:
                out = self.answerer.answer(question, lessons, previous, feedback)
                say("[%s] ANSWERING -> EVALUATOR  attempt %d (%.0f ms): %s", qid, n, out["ms"], short(out["answer"], 220))
            ev = self.evaluator.evaluate(question, out["answer"])
            say("[%s] EVALUATOR -> %s  %s%s", qid, ev.result, ev.explanation,
                f" | pattern={ev.failure_pattern}" if ev.failure_pattern else "")
            if ev.feedback and n < self.max_attempts:
                say("[%s]    feedback: %s", qid, ev.feedback)
            attempts.append({"attempt": n, "answer": out["answer"], "model_ms": out["ms"],
                             "forced": out.get("forced", False), **ev.to_dict()})
            if ev.result == "PASS":
                break
            previous, feedback = out["answer"], ev.feedback
        new_lesson = None
        if self.learn and attempts[0]["result"] == "REVISE":
            new_lesson = self.store.record_failure(attempts[0]["failure_pattern"], qid, self.dataset)
            if new_lesson:
                say("[%s] NEW LESSON %s created (pattern %s repeated in %s): %s", qid, new_lesson["lesson_id"],
                    new_lesson["pattern"], new_lesson["source"]["failed_question_ids"], new_lesson["correction"])
        if self.store and lessons:
            self.store.mark_used(lessons)
        final = attempts[-1]
        rec = {"id": qid, "question": question, "lessons_loaded": [x["lesson_id"] for x in lessons],
               "attempts": attempts, "n_attempts": len(attempts), "final_answer": final["answer"],
               "final_result": final["result"], "correct": final["result"] == "PASS",
               "latency_ms": round((time.perf_counter() - t0) * 1000, 1), "new_lesson": new_lesson and new_lesson["lesson_id"]}
        say("[%s] FINAL: %s after %d attempt(s), %.0f ms", qid, rec["final_result"], rec["n_attempts"], rec["latency_ms"])
        return rec


def summarize(records: list[dict]) -> dict:
    """Correct / incorrect / average attempts / average latency."""
    return {"correct": sum(r["correct"] for r in records), "incorrect": sum(not r["correct"] for r in records),
            "avg_attempts": round(statistics.mean(r["n_attempts"] for r in records), 2),
            "avg_latency_ms": round(statistics.mean(r["latency_ms"] for r in records), 1)}


# ------------------------------------------------------------------------- steps ----
def step_controlled(answerer, evaluator, log) -> dict:  # noqa: ANN001
    """4.1 - controlled case: the first answer is intentionally incomplete."""
    log.info("==== 4.1 controlled revision sequence ====")
    system = TwoAgentSystem(answerer, evaluator, log, max_attempts=2)
    rec = system.run(*CONTROLLED_QUESTION, forced_first=CONTROLLED_BAD_FIRST)
    log.info("sequence: question -> initial answer -> REVISE + feedback -> revised answer -> %s | attempts=%d | "
             "final response: %s", rec["final_result"], rec["n_attempts"], rec["final_answer"])
    write_json("part4_controlled.json", rec)
    return rec


def step_train(answerer, evaluator, log, min_repeats: int) -> dict:  # noqa: ANN001
    """Training set with repair + lesson creation; later questions reuse lessons (4.2)."""
    log.info("==== training_data.json: Evaluator Repair + lesson creation (min_repeats=%d) ====", min_repeats)
    store = LessonStore(LESSONS, min_repeats=min_repeats)
    store.reset()
    system = TwoAgentSystem(answerer, evaluator, log, store, statuses=("candidate", "kept"), max_attempts=2,
                            learn=True, dataset="training")
    records = [system.run(qid, q) for qid, q in load_questions("training_data.json")]
    created = {r["new_lesson"]: r["id"] for r in records if r["new_lesson"]}
    reuse = None
    order = [r["id"] for r in records]
    for r in records:
        for lid in r["lessons_loaded"]:
            if lid in created and order.index(r["id"]) > order.index(created[lid]):
                reuse = {"lesson": next(x for x in store.lessons if x["lesson_id"] == lid),
                         "created_after_failed_question": created[lid], "reused_in": r}
                break
        if reuse:
            break
    if reuse:
        r = reuse["reused_in"]
        log.info("==== 4.2 lesson reuse: %s created after %s failed; loaded for the later question %s ====",
                 reuse["lesson"]["lesson_id"], reuse["created_after_failed_question"], r["id"])
        log.info("   later question: %s", r["question"])
        log.info("   lessons loaded: %s -> first attempt %s, final %s in %d attempt(s)", r["lessons_loaded"],
                 r["attempts"][0]["result"], r["final_result"], r["n_attempts"])
        log.info("   answer: %s", r["final_answer"])
    log.info("training summary: %s | lessons: %s", summarize(records),
             [(x["lesson_id"], x["pattern"], x["use_count"]) for x in store.lessons])
    write_json("part4_training.json", {"records": records, "reuse_example": reuse, "lessons": store.lessons})
    return {"records": records, "reuse": reuse}


def step_validate(answerer, evaluator, log) -> list[dict]:  # noqa: ANN001
    """4.3 - each candidate lesson: validation_data before vs after; keep only without regression."""
    log.info("==== 4.3 validation_data.json: keep a lesson only if nothing regresses ====")
    store = LessonStore(LESSONS)
    questions = load_questions("validation_data.json")
    decisions = []
    for lesson in [x for x in store.lessons if x["status"] == "candidate"]:
        # attempts=1 isolates the lesson's own effect (repair would hide first-answer differences)
        before_sys = TwoAgentSystem(answerer, evaluator, log, store, statuses=("kept",), max_attempts=1)
        before = {qid: before_sys.run(qid, q, quiet=True) for qid, q in questions}
        lesson["status"] = "trial"
        after_sys = TwoAgentSystem(answerer, evaluator, log, store, statuses=("kept", "trial"), max_attempts=1)
        after = {qid: after_sys.run(qid, q, quiet=True) for qid, q in questions}
        lesson["status"] = "candidate"
        fails_before = [q for q, r in before.items() if not r["correct"]]
        fails_after = [q for q, r in after.items() if not r["correct"]]
        regressions = [q for q in before if before[q]["correct"] and not after[q]["correct"]]
        unrelated = [q for q in after if "no_record" in after[q]["attempts"][0]["expected"]]
        unsupported = [q for q in unrelated if after[q]["attempts"][0]["failure_pattern"] == "unsupported_answer"]
        new_unsupported = [q for q in unsupported if before[q]["correct"]]      # caused by this lesson
        keep = len(fails_after) <= len(fails_before) and not regressions and not new_unsupported
        validation = {"dataset": "validation", "failures_before": fails_before, "failures_after": fails_after,
                      "regressions": regressions, "unrelated_questions": unrelated,
                      "unsupported_after": unsupported, "new_unsupported": new_unsupported, "decision": "kept" if keep else "rejected",
                      "per_question": {q: [before[q]["final_result"], after[q]["final_result"]] for q in before}}
        store.set_status(lesson["lesson_id"], "kept" if keep else "rejected", validation)
        log.info("%s (%s): failures %d -> %d %s | regressions %s | unrelated %s: unsupported after %s, new %s -> %s",
                 lesson["lesson_id"], lesson["pattern"], len(fails_before), len(fails_after), fails_after,
                 regressions or "none", unrelated, unsupported or "none", new_unsupported or "none",
                 "KEPT" if keep else "REJECTED (removed)")
        for q in before:
            if before[q]["final_result"] != after[q]["final_result"]:
                log.info("   %s changed %s -> %s: %s", q, before[q]["final_result"], after[q]["final_result"],
                         short(after[q]["final_answer"], 140))
        decisions.append({"lesson_id": lesson["lesson_id"], **validation,
                          "before": list(before.values()), "after": list(after.values())})
    if not decisions:
        log.info("no candidate lessons to validate (run train first)")
    write_json("part4_validation.json", decisions)
    return decisions


def step_test(answerer, evaluator, log) -> dict:  # noqa: ANN001
    """4.4 - all four variants on the held-out test set; lessons are read-only."""
    log.info("==== 4.4 test_data.json on four variants (lessons frozen, test data never used for lessons) ====")
    questions = load_questions("test_data.json")
    results = {}
    for name, (max_attempts, statuses) in VARIANTS.items():
        store = LessonStore(LESSONS, frozen=True)
        system = TwoAgentSystem(answerer, evaluator, log, store, statuses=statuses, max_attempts=max_attempts)
        log.info("---- variant: %s (max attempts %d, lessons %s) ----", name, max_attempts,
                 [x["lesson_id"] for x in store.lessons if x["status"] in statuses] or "none")
        recs = [system.run(qid, q, quiet=True) for qid, q in questions]
        for r in recs:
            log.info("   %s %-6s attempts=%d lessons=%s | %s", r["id"], r["final_result"], r["n_attempts"],
                     r["lessons_loaded"] or "-", short(r["final_answer"], 100))
        results[name] = {"summary": summarize(recs), "records": recs}
    log.info("==== results table (test_data.json, %d questions) ====", len(questions))
    log.info("%-22s | correct | incorrect | avg attempts | avg latency (ms)", "variant")
    for name, res in results.items():
        s = res["summary"]
        log.info("%-22s | %7d | %9d | %12.2f | %16.1f", name, s["correct"], s["incorrect"], s["avg_attempts"],
                 s["avg_latency_ms"])
    write_json("part4_test_results.json", results)
    return results


def main() -> None:
    """CLI."""
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["controlled", "train", "validate", "test", "all"])
    ap.add_argument("--min-repeats", type=int, default=2)
    ap.add_argument("--fake-model", action="store_true", help="offline test only")
    args = ap.parse_args()
    log = setup_logging("part4")
    banner(log, "Part 4 - Answering + Evaluator agents")
    answerer = AnsweringAgent(make_model(args.fake_model), SNAPSHOT, REFERENCE)
    evaluator = EvaluatorAgent(REFERENCE)
    if args.step in ("controlled", "all"):
        step_controlled(answerer, evaluator, log)
    if args.step in ("train", "all"):
        step_train(answerer, evaluator, log, args.min_repeats)
    if args.step in ("validate", "all"):
        step_validate(answerer, evaluator, log)
    if args.step in ("test", "all"):
        step_test(answerer, evaluator, log)


if __name__ == "__main__":
    main()
