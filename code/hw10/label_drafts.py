"""HW10 Part 3.1 - helper for HAND labelling: shows each draft and stores the label YOU type.

    python code/hw10/label_drafts.py              # walks C01..C20, skips cases already labelled
    python code/hw10/label_drafts.py --redo C07   # change one label (only before committing!)

No model is involved: the script only displays eval_cases.json and writes your number into human_labels.csv.

Labelling guide (helpfulness of the Writer draft for the rider, 1-5):
  5 excellent  - answers exactly what was asked; every fact matches the records in the question; nothing missing
  4 good       - correct and useful, small gap or some unneeded text
  3 okay       - partly answers; generic, or one minor inaccuracy / missing piece
  2 poor       - mostly unhelpful: vague, wrong emphasis, asks the rider for info instead of answering
  1 very poor  - wrong facts, off-topic, or no real answer
"""
import argparse
import csv
import json
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hw10_config as cfg  # noqa: E402


def main() -> None:
    """Interactive labelling."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--redo")
    ap.add_argument("--labeler", default=cfg.STUDENT_NAME)
    args = ap.parse_args()
    cases = json.loads(cfg.EVAL_CASES.read_text(encoding="utf-8"))["cases"]
    rows = list(csv.DictReader(open(cfg.HUMAN_LABELS, encoding="utf-8")))
    by_id = {r["case_id"]: r for r in rows}
    print(__doc__.split("Labelling guide", 1)[1])
    for c in cases:
        row = by_id[c["case_id"]]
        if row["human_label"] and c["case_id"] != args.redo:
            continue
        print("=" * 100)
        print(f"{c['case_id']}  ({c['question_type']})")
        print("QUESTION:\n" + textwrap.indent(c["question"], "  "))
        print("DRAFT:\n" + textwrap.indent(textwrap.fill(c["draft"], 96), "  "))
        while True:
            ans = input(f"Your label for {c['case_id']} (1-5, q = save and quit): ").strip().lower()
            if ans == "q":
                break
            if ans in {"1", "2", "3", "4", "5"}:
                row["human_label"], row["labeler"] = ans, args.labeler
                break
            print("  please type 1, 2, 3, 4 or 5")
        if ans == "q":
            break
    with open(cfg.HUMAN_LABELS, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["case_id", "human_label", "labeler", "question_short"])
        w.writeheader()
        w.writerows(rows)
    done = sum(bool(r["human_label"]) for r in rows)
    print(f"\nsaved {cfg.HUMAN_LABELS.relative_to(cfg.REPO_ROOT)}: {done}/{len(rows)} labelled")
    if done == len(rows):
        print("All 20 labelled. Commit BOTH files now, before any judge run:\n"
              "  git add code/hw10/eval_cases.json code/hw10/human_labels.csv && "
              "git commit -m \"HW10 Part 3.1: frozen eval cases + human labels\"")


if __name__ == "__main__":
    main()
