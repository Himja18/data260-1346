"""HW10 Part 3.2-3.3 - judge vs human labels (Spearman, MAD) and repeatability (3 runs).

    python code/hw10/run_judge_validation.py

Refuses to run unless eval_cases.json and human_labels.csv are complete, committed, and unchanged since the
commit (so the labels provably existed before any judge score). The judge is the same GEval Writer
Helpfulness metric used in Part 2, with the documented settings in judge.judge_settings().
Outputs: reports/hw10/judge_validation.json and reports/hw10/raw/judge_scores.csv (raw per-case data).
"""
import csv
import itertools
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hw10_config as cfg  # noqa: E402
from judge import judge_settings, score  # noqa: E402

RUNS = 3


def ranks(xs: list[float]) -> list[float]:
    """Average ranks (ties share the mean rank)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a: list[float], b: list[float]) -> float:
    """Spearman rho = Pearson correlation of the average ranks."""
    ra, rb = ranks(a), ranks(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else float("nan")


def git_proof(path: Path) -> dict:
    """Commit that added the file, and whether it is unchanged since (labels frozen before judging)."""
    rel = str(path.relative_to(cfg.REPO_ROOT))

    def git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=cfg.REPO_ROOT, capture_output=True, text=True).stdout.strip()
    commit = git("log", "-1", "--format=%H %cI", "--", rel)
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=cfg.REPO_ROOT).returncode == 0
    return {"file": rel, "last_commit": commit or None, "unchanged_since_commit": clean and bool(commit)}


def main() -> None:  # noqa: PLR0915
    """Validate the judge."""
    log = cfg.setup_logging("judge-valid")
    cases = json.loads(cfg.EVAL_CASES.read_text(encoding="utf-8"))["cases"]
    labels = {r["case_id"]: r["human_label"].strip() for r in csv.DictReader(open(cfg.HUMAN_LABELS, encoding="utf-8"))}
    missing = [c["case_id"] for c in cases if labels.get(c["case_id"]) not in {"1", "2", "3", "4", "5"}]
    if missing:
        raise SystemExit(f"human labels missing or invalid for {missing} - label by hand first (label_drafts.py)")
    proofs = [git_proof(cfg.EVAL_CASES), git_proof(cfg.HUMAN_LABELS)]
    if not all(p["unchanged_since_commit"] for p in proofs):
        raise SystemExit(f"commit eval_cases.json and human_labels.csv (unchanged) before judging: {proofs}")
    log.info("labels frozen: %s", proofs)
    settings = judge_settings()
    log.info("judge settings: %s", settings)

    runs: list[dict[str, dict]] = []
    for run in range(1, RUNS + 1):
        t0 = time.time()
        res = {}
        for c in cases:
            s = score("writer_helpfulness", c["question"], c["draft"])
            res[c["case_id"]] = s
            log.info("run %d %s human=%s judge=%s (raw %s) %s", run, c["case_id"], labels[c["case_id"]], s["score"],
                     s["score_raw"], s["error"] or "")
        runs.append(res)
        log.info("run %d done in %.0f s", run, time.time() - t0)

    ids = [c["case_id"] for c in cases]
    human = [int(labels[i]) for i in ids]
    ok_ids = [i for i in ids if all(r[i]["status"] == "ok" for r in runs)]
    failed = [i for i in ids if i not in ok_ids]
    j1 = [runs[0][i]["score"] for i in ok_ids]
    h_ok = [int(labels[i]) for i in ok_ids]
    jmean = [statistics.mean(r[i]["score"] for r in runs) for i in ok_ids]
    rho1 = spearman(h_ok, j1)
    rho_mean = spearman(h_ok, jmean)
    try:
        from scipy.stats import spearmanr
        p_value = float(spearmanr(h_ok, j1).pvalue)
    except Exception:  # noqa: BLE001
        p_value = None
    mad1 = statistics.mean(abs(a - b) for a, b in zip(h_ok, j1, strict=True))
    mad_runs = [statistics.mean(abs(int(labels[i]) - r[i]["score"]) for i in ok_ids) for r in runs]
    rhos = [spearman(h_ok, [r[i]["score"] for i in ok_ids]) for r in runs]

    pair_changes, changed_cases, ranges = [], [], {}
    for i in ok_ids:
        vals = [r[i]["score"] for r in runs]
        ranges[i] = max(vals) - min(vals)
        if ranges[i]:
            changed_cases.append(i)
        pair_changes += [abs(a - b) for a, b in itertools.combinations(vals, 2)]
    changed_pairs = sum(1 for x in pair_changes if x)
    raw_pair = [abs(a - b) for i in ok_ids for a, b in
                itertools.combinations([r[i]["score_raw"] for r in runs], 2)]

    summary = {
        "n_cases": len(ids), "n_scored_all_runs": len(ok_ids), "failed_cases": failed,
        "spearman_run1": round(rho1, 3), "spearman_run1_p_value": None if p_value is None else round(p_value, 4),
        "spearman_per_run": [round(x, 3) for x in rhos], "spearman_mean_of_3_runs": round(rho_mean, 3),
        "mad_run1": round(mad1, 3), "mad_per_run": [round(x, 3) for x in mad_runs],
        "repeatability": {
            "cases_with_any_change": len(changed_cases), "cases_with_any_change_pct": round(100 * len(changed_cases) / len(ok_ids), 1),
            "changed_cases": changed_cases,
            "pairwise_comparisons": len(pair_changes), "pairwise_changed": changed_pairs,
            "pairwise_changed_pct": round(100 * changed_pairs / len(pair_changes), 1),
            "mean_abs_change": round(statistics.mean(pair_changes), 3), "max_abs_change": max(pair_changes),
            "mean_abs_change_raw": round(statistics.mean(raw_pair), 3), "max_abs_change_raw": round(max(raw_pair), 2),
        },
        "human_label_distribution": {k: human.count(k) for k in range(1, 6)},
        "judge_run1_distribution": {k: j1.count(k) for k in range(1, 6)},
    }
    out = {"settings": settings, "labels_frozen": proofs, "summary": summary,
           "cases": [{"case_id": i, "question_type": next(c["question_type"] for c in cases if c["case_id"] == i),
                      "human": int(labels[i]),
                      "judge": [r[i]["score"] for r in runs], "judge_raw": [r[i]["score_raw"] for r in runs],
                      "reasons": [r[i]["reason"] for r in runs], "errors": [r[i]["error"] for r in runs]}
                     for i in ids]}
    cfg.ensure_dirs()
    cfg.JUDGE_VALIDATION.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(cfg.RAW_DIR / "judge_scores.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id", "human_label", "judge_run1", "judge_run2", "judge_run3",
                    "raw_run1", "raw_run2", "raw_run3", "abs_diff_run1"])
        for row in out["cases"]:
            w.writerow([row["case_id"], row["human"], *row["judge"], *row["judge_raw"],
                        "" if row["judge"][0] is None else abs(row["human"] - row["judge"][0])])
    log.info("==== judge vs human (n=%d) ====", len(ok_ids))
    log.info("Spearman rho (run 1) = %.3f (p=%s) | per run %s | mean of 3 runs %.3f", rho1, summary["spearman_run1_p_value"],
             summary["spearman_per_run"], rho_mean)
    log.info("Mean absolute difference (run 1) = %.3f | per run %s", mad1, summary["mad_per_run"])
    rep = summary["repeatability"]
    log.info("Repeatability: %d/%d cases changed across 3 runs (%.1f%%); %d/%d pairwise comparisons changed; "
             "mean |change| %.3f, max |change| %d (raw: mean %.3f, max %.2f)", rep["cases_with_any_change"],
             len(ok_ids), rep["cases_with_any_change_pct"], rep["pairwise_changed"], rep["pairwise_comparisons"],
             rep["mean_abs_change"], rep["max_abs_change"], rep["mean_abs_change_raw"], rep["max_abs_change_raw"])
    log.info("human labels %s | judge run 1 %s", summary["human_label_distribution"], summary["judge_run1_distribution"])
    log.info("saved %s and reports/hw10/raw/judge_scores.csv", cfg.JUDGE_VALIDATION.relative_to(cfg.REPO_ROOT))


if __name__ == "__main__":
    main()
