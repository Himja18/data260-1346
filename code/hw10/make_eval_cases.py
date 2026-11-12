"""HW10 Part 3.1 - freeze 20 Writer drafts from this system into eval_cases.json + a human_labels.csv to fill in.

    python code/hw10/make_eval_cases.py            # read real drafts from s1346_drafts (HW8/HW9 runs)
    python code/hw10/make_eval_cases.py --force    # overwrite (only before the files are committed)

Selection (deterministic): every draft on s1346_drafts, newest first, one per distinct question, skipping empty
drafts, until 20 are chosen; questions are spread across incident look-ups, how-to questions and off-domain ones
so the set covers good and bad drafts. The human labels are NOT generated: human_labels.csv is written with an
empty human_label column that the student fills in by hand (1 = very poor ... 5 = excellent) and commits,
together with eval_cases.json, BEFORE any judge run (run_judge_validation.py refuses otherwise).
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hw10_config as cfg  # noqa: E402
from kafka_common import read_topic  # noqa: E402

N_CASES = 20


def kind(question: str) -> str:
    """Rough question type, only used to spread the selection."""
    q = question.lower()
    if "inc-" in q:
        return "incident lookup"
    if any(w in q for w in ("report", "contact", "category", "difference", "detour", "reroute", "how long",
                            "cleared", "information", "details")):
        return "transit how-to"
    return "off-domain"


def main() -> None:
    """Build the two files."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    log = cfg.setup_logging("eval-cases")
    if (cfg.EVAL_CASES.exists() or cfg.HUMAN_LABELS.exists()) and not args.force:
        raise SystemExit(f"{cfg.EVAL_CASES.name} / {cfg.HUMAN_LABELS.name} already exist - they are frozen. "
                         "Use --force only if they were never committed.")
    records = read_topic(cfg.cfg8.DRAFTS_TOPIC, idle_s=5.0, max_s=120.0)
    log.info("read %d records from %s", len(records), cfg.cfg8.DRAFTS_TOPIC)
    seen, by_kind = set(), {"incident lookup": [], "transit how-to": [], "off-domain": []}
    for rec in sorted(records, key=lambda r: (r["partition"], r["offset"]), reverse=True):
        v = rec["value"]
        if not isinstance(v, dict) or not str(v.get("draft") or "").strip() or not v.get("question"):
            continue
        q = str(v["question"]).strip()
        key = q.split("\n")[0].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        by_kind[kind(q)].append({"trace_id": v.get("correlation_id"), "question": q, "plan": v.get("plan") or [],
                                 "draft": str(v["draft"]).strip(), "written_by": v.get("written_by"),
                                 "kafka": {"topic": cfg.cfg8.DRAFTS_TOPIC, "partition": rec["partition"],
                                           "offset": rec["offset"]}, "question_type": kind(q)})
    quota = {"incident lookup": 9, "transit how-to": 8, "off-domain": 3}
    chosen = []
    for k, n in quota.items():
        chosen += by_kind[k][:n]
    rest = [c for k in by_kind for c in by_kind[k] if c not in chosen]
    chosen += rest[: N_CASES - len(chosen)]
    if len(chosen) < N_CASES:
        raise SystemExit(f"only {len(chosen)} distinct drafts on {cfg.cfg8.DRAFTS_TOPIC}; run more questions first "
                         "(e.g. make hw09-part2) and try again")
    cases = [{"case_id": f"C{i:02d}", **c} for i, c in enumerate(chosen[:N_CASES], 1)]
    cfg.EVAL_CASES.write_text(json.dumps({"description": "20 Writer drafts from the s1346 Planner/Writer/Reviewer "
                                                         "pipeline (frozen for HW10 Part 3)",
                                          "source_topic": cfg.cfg8.DRAFTS_TOPIC, "cases": cases},
                                         indent=2, ensure_ascii=False), encoding="utf-8")
    with open(cfg.HUMAN_LABELS, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id", "human_label", "labeler", "question_short"])
        for c in cases:
            w.writerow([c["case_id"], "", "", c["question"].split("\n")[0][:90]])
    log.info("wrote %s (%d cases: %s) and %s with EMPTY human_label - fill it in by hand",
             cfg.EVAL_CASES.relative_to(cfg.REPO_ROOT), len(cases),
             {k: sum(c["question_type"] == k for c in cases) for k in quota},
             cfg.HUMAN_LABELS.relative_to(cfg.REPO_ROOT))
    for c in cases:
        log.info("%s [%s] %s", c["case_id"], c["question_type"], c["question"].split("\n")[0][:100])


if __name__ == "__main__":
    main()
