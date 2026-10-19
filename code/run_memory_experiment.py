"""DATA-260 HW6 Part 3 - what memory costs (SHORT_TERM_N sweep + memory-saving policy).

Runs the fixed 30-message conversation (reports/hw06/cases/conversation_30.json)
through POST /api/chat in a FRESH user + session per setting, then asks the five
probes from reports/hw06/memory_probes.yaml and scores them with the 1-5 rubric.

Settings (labels):
  n4      SHORT_TERM_N = 4
  n12     SHORT_TERM_N = 12
  n30     SHORT_TERM_N = 30
  policy  SHORT_TERM_N = 30 + compress_assistant (older assistant turns cut to 1 sentence)

Run (backend on 8446, MongoDB + Ollama up):
    python code/run_memory_experiment.py                 # all four settings (~30-60 min on an M2)
    python code/run_memory_experiment.py --only n4       # one setting; results are merged

Outputs (reports/hw06/raw/): turns_<label>.csv, probes_<label>.json,
memory_turns.csv, probe_scores.csv, memory_summary.json. Progress -> reports/hw06/RUN_LOG.txt
"""
import argparse
import csv
import json
import re
import statistics
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml

REPO = Path(__file__).resolve().parents[1]
HW = REPO / "reports" / "hw06"
RAW = HW / "raw"
RUN_LOG = HW / "RUN_LOG.txt"
CONVERSATION = HW / "cases" / "conversation_30.json"
PROBES = HW / "memory_probes.yaml"
BASE = "http://127.0.0.1:8446"
SEED = 1346

SETTINGS = {
    "n4": {"short_term_n": 4, "memory_policy": "none"},
    "n12": {"short_term_n": 12, "memory_policy": "none"},
    "n30": {"short_term_n": 30, "memory_policy": "none"},
    "policy": {"short_term_n": 30, "memory_policy": "compress_assistant"},
}
LABELS = {"n4": "SHORT_TERM_N=4", "n12": "SHORT_TERM_N=12", "n30": "SHORT_TERM_N=30",
          "policy": "Compression policy (N=30 + compress_assistant)"}

TURN_FIELDS = ["setting", "phase", "turn", "short_term_n", "memory_policy", "prompt_tokens",
               "prompt_tokens_full", "completion_tokens", "tokens_system_primer",
               "tokens_long_term_summary", "tokens_short_term_window", "tokens_episodic_facts",
               "tokens_current_message", "aux_prompt_tokens", "aux_completion_tokens",
               "short_term_count", "episodes_retrieved", "episodes_stored",
               "session_summary_updated", "lifetime_summary_updated", "model_latency_ms",
               "latency_ms", "client_latency_ms", "token_count_method"]


def log(msg: str) -> None:
    """Print and append a timestamped line to RUN_LOG.txt."""
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(RUN_LOG, "a") as fh:
        fh.write(line + "\n")


def score_probe(answer: str, probe: dict, unknown_patterns: list) -> tuple:
    """Apply the 1-5 rubric. Returns (score, reason)."""
    text = answer.lower()
    groups = probe.get("required", [])
    hits = sum(1 for g in groups if any(re.search(p, text) for p in g))
    forbidden = [p for p in probe.get("forbidden", []) if re.search(p, text)]
    unknown = any(re.search(p, text) for p in unknown_patterns)
    if groups and hits == len(groups):
        return (4, f"all required, but mentions {forbidden}") if forbidden else (5, "all required")
    if groups and hits * 2 >= len(groups) and hits > 0:
        return 3, f"{hits}/{len(groups)} required"
    if unknown or (hits > 0 and not forbidden):
        return 2, "says it does not know" if unknown else f"{hits}/{len(groups)} required"
    return 1, f"wrong/hallucinated{' (' + ','.join(forbidden) + ')' if forbidden else ''}"


def chat(session: requests.Session, user_id: str, session_id: str, message: str, cfg: dict) -> dict:
    """One POST /api/chat call; adds client-side latency."""
    t0 = time.perf_counter()
    r = session.post(f"{BASE}/api/chat", json={"user_id": user_id, "session_id": session_id,
                                                "message": message, **cfg}, timeout=600)
    r.raise_for_status()
    body = r.json()
    body["usage"]["client_latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return body


def run_setting(label: str, conversation: list, probes: dict) -> dict:
    """Fresh user + session, 30 messages, 5 probes. Returns the summary dict."""
    cfg = SETTINGS[label]
    user_id = f"s1346-exp-{label}"
    session_id = f"{label}-seed{SEED}-{int(time.time())}"
    http = requests.Session()
    deleted = http.delete(f"{BASE}/api/memory/{user_id}", timeout=30).json()["deleted"]
    log(f"--- setting {label} ({LABELS[label]}) user={user_id} session={session_id} "
        f"cleared={deleted}")

    rows = []
    for i, msg in enumerate(conversation, start=1):
        body = chat(http, user_id, session_id, msg, cfg)
        u = body["usage"]
        rows.append({"setting": label, "phase": "conversation", **{k: u.get(k) for k in TURN_FIELDS
                                                                  if k not in ("setting", "phase")}})
        log(f"{label} turn {i:02d}: prompt_full={u['prompt_tokens_full']} "
            f"(ollama={u['prompt_tokens']}) completion={u['completion_tokens']} "
            f"window={u['short_term_count']} epi={u['episodes_retrieved']} "
            f"latency={u['latency_ms']:.0f}ms")

    probe_results = []
    for p in probes["probes"]:
        body = chat(http, user_id, session_id, p["question"], cfg)
        u = body["usage"]
        rows.append({"setting": label, "phase": "probe", **{k: u.get(k) for k in TURN_FIELDS
                                                           if k not in ("setting", "phase")}})
        score, reason = score_probe(body["reply"], p, probes.get("unknown_patterns", []))
        probe_results.append({"setting": label, "probe_id": p["id"], "question": p["question"],
                              "expected": p["expected"], "answer": body["reply"], "score": score,
                              "reason": reason,
                              "episodic_used": [f["fact"] for f in body["memory_used"]["episodic"]],
                              "short_term_count": body["memory_used"]["short_term"]["count"]})
        log(f"{label} {p['id']}: score={score} ({reason}) answer={body['reply'][:120]!r}")

    with open(RAW / f"turns_{label}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=TURN_FIELDS)
        w.writeheader()
        w.writerows(rows)
    (RAW / f"probes_{label}.json").write_text(json.dumps(probe_results, indent=2))

    conv = [r for r in rows if r["phase"] == "conversation"]
    mean = lambda key: round(statistics.mean(float(r[key]) for r in conv), 1)  # noqa: E731
    summary = {
        "setting": label, "label": LABELS[label], **cfg, "user_id": user_id, "session_id": session_id,
        "turns": len(conv),
        "mean_prompt_tokens_full": mean("prompt_tokens_full"),
        "mean_prompt_tokens_ollama": mean("prompt_tokens"),
        "mean_completion_tokens": mean("completion_tokens"),
        "mean_tokens_system_primer": mean("tokens_system_primer"),
        "mean_tokens_long_term_summary": mean("tokens_long_term_summary"),
        "mean_tokens_short_term_window": mean("tokens_short_term_window"),
        "mean_tokens_episodic_facts": mean("tokens_episodic_facts"),
        "mean_aux_prompt_tokens": mean("aux_prompt_tokens"),
        "mean_aux_completion_tokens": mean("aux_completion_tokens"),
        "mean_latency_ms": mean("latency_ms"),
        "mean_model_latency_ms": mean("model_latency_ms"),
        "mean_probe_score": round(statistics.mean(p["score"] for p in probe_results), 2),
        "probe_scores": {p["probe_id"]: p["score"] for p in probe_results},
        "token_count_method": conv[0]["token_count_method"],
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    log(f"{label} SUMMARY: mean_prompt_full={summary['mean_prompt_tokens_full']} "
        f"mean_latency={summary['mean_latency_ms']}ms probe={summary['mean_probe_score']} "
        f"{summary['probe_scores']}")
    return summary


def merge_outputs() -> None:
    """Rebuild the combined CSVs from every per-setting file present."""
    turn_rows, probe_rows = [], []
    for label in SETTINGS:
        tf, pf = RAW / f"turns_{label}.csv", RAW / f"probes_{label}.json"
        if tf.exists():
            turn_rows += list(csv.DictReader(open(tf)))
        if pf.exists():
            probe_rows += json.loads(pf.read_text())
    if turn_rows:
        with open(RAW / "memory_turns.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=TURN_FIELDS)
            w.writeheader()
            w.writerows(turn_rows)
    if probe_rows:
        with open(RAW / "probe_scores.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["setting", "probe_id", "score", "reason", "expected",
                                               "answer", "short_term_count", "episodic_used"])
            w.writeheader()
            for p in probe_rows:
                w.writerow({k: (json.dumps(p[k]) if k == "episodic_used" else p[k])
                            for k in w.fieldnames})


def main() -> None:
    """CLI entry point."""
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=list(SETTINGS), action="append",
                    help="run only these settings (repeatable)")
    ap.add_argument("--base-url", default=BASE)
    args = ap.parse_args()
    BASE = args.base_url

    RAW.mkdir(parents=True, exist_ok=True)
    conversation = json.loads(CONVERSATION.read_text())["messages"]
    probes = yaml.safe_load(PROBES.read_text())
    assert len(conversation) == 30 and len(probes["probes"]) == 5

    health = requests.get(f"{BASE}/health", timeout=5).json()
    log(f"=== HW6 Part 3 memory experiment | backend={health} | seed={SEED}")

    summary_path = RAW / "memory_summary.json"
    summaries = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    for label in args.only or list(SETTINGS):
        summaries[label] = run_setting(label, conversation, probes)
        summary_path.write_text(json.dumps(summaries, indent=2))   # save after every setting
    merge_outputs()
    log(f"Saved {summary_path.relative_to(REPO)}, memory_turns.csv, probe_scores.csv")


if __name__ == "__main__":
    main()
