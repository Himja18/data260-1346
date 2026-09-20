"""
HW3 Part 2 — Generate METRICS.md from raw/*.json pipeline results.

Usage:
    python3 generate_metrics.py

Reads:
    raw/token_results.json
    raw/semantic_results.json
    raw/sentence_window_results.json

Writes:
    METRICS.md
"""

import json
import os

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "raw")
OUT_PATH = os.path.join(BASE_DIR, "METRICS.md")

PIPELINES = ["token", "semantic", "sentence_window"]
PIPELINE_LABELS = {
    "token": "Token-based",
    "semantic": "Semantic",
    "sentence_window": "Sentence-window",
}


def load(name):
    path = os.path.join(RAW_DIR, f"{name}_results.json")
    with open(path, "r") as f:
        return json.load(f)


def main():
    data = {name: load(name) for name in PIPELINES}

    lines = []
    lines.append("# METRICS.md — HW3 Part 2 Chunking Comparison\n")
    lines.append("Domain 2: Municipal Transit Incidents | SID4 = 1346\n")

    # --- Summary table ---
    lines.append("## Pipeline Summary\n")
    lines.append("| Pipeline | # Chunks | Time (s) | Questions Hit Expected Source | Hit Rate |")
    lines.append("|---|---|---|---|---|")
    for name in PIPELINES:
        d = data[name]
        n_hit = sum(1 for r in d["results"] if r["hit_expected_source_file"])
        n_total = len(d["results"])
        lines.append(
            f"| {PIPELINE_LABELS[name]} | {d['num_chunks']} | {d['elapsed_seconds']} "
            f"| {n_hit}/{n_total} | {n_hit/n_total*100:.0f}% |"
        )
    lines.append("")

    # --- Per-question breakdown ---
    lines.append("## Per-Question Results\n")
    q_ids = [r["question_id"] for r in data["token"]["results"]]
    for qid in q_ids:
        q_data = {name: next(r for r in data[name]["results"] if r["question_id"] == qid) for name in PIPELINES}
        sample = q_data["token"]
        lines.append(f"### {qid} ({sample['question_type']})")
        lines.append(f"**Question:** {sample['question']}\n")
        lines.append(f"**Expected source(s):** `{', '.join(sample['expected_source_files'])}`\n")
        lines.append("| Pipeline | Hit expected source? | Top-1 retrieved file | Top-1 score | Top-2 score | Top-3 score |")
        lines.append("|---|---|---|---|---|---|")
        for name in PIPELINES:
            r = q_data[name]
            chunks = r["retrieved_chunks"]
            top1 = chunks[0] if len(chunks) > 0 else None
            scores = [c["score"] for c in chunks]
            scores_fmt = [f"{s:.3f}" if s is not None else "N/A" for s in scores]
            while len(scores_fmt) < 3:
                scores_fmt.append("--")
            hit = "✅" if r["hit_expected_source_file"] else "❌"
            top1_file = top1["source_file"] if top1 else "N/A"
            lines.append(
                f"| {PIPELINE_LABELS[name]} | {hit} | `{top1_file}` | {scores_fmt[0]} | {scores_fmt[1]} | {scores_fmt[2]} |"
            )
        lines.append("")

    # --- Adversarial question deep-dive (q4 specifically, if present) ---
    adversarial_qs = [qid for qid in q_ids if data["token"]["results"][q_ids.index(qid)]["question_type"] == "adversarial"]
    if adversarial_qs:
        lines.append("## Adversarial Question Deep-Dive\n")
        for qid in adversarial_qs:
            lines.append(f"### {qid}\n")
            for name in PIPELINES:
                r = next(x for x in data[name]["results"] if x["question_id"] == qid)
                lines.append(f"**{PIPELINE_LABELS[name]}** — hit expected source: {r['hit_expected_source_file']}")
                for c in r["retrieved_chunks"]:
                    snippet = c["text"][:150].replace("\n", " ")
                    lines.append(f"  - rank {c['rank']}, score {c['score']:.4f}, file `{c['source_file']}`: {snippet}...")
                lines.append("")

    with open(OUT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"METRICS.md written to {OUT_PATH}")
    print(f"Total lines: {len(lines)}")


if __name__ == "__main__":
    main()