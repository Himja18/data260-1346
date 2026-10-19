"""HW6 smoke test. Writes reports/hw06/verification.json.

    make verify-hw06        (or: python verify_hw06.py)

Needs the backend running on PORT_BASE 8446 (cd code/backend && python main.py), MongoDB on
127.0.0.1:27017 and Ollama with qwen2.5:3b. Behaviour checks only (status codes, fields,
counts) - never exact model wording. Never modifies application code: the temporary incident
document and the temporary chat user it creates are deleted again, and the consolidation check
runs on a copy in a temporary directory.
"""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml

REPO = Path(__file__).resolve().parent
HW = REPO / "reports" / "hw06"
RAW = HW / "raw"
sys.path.insert(0, str(REPO / "code"))

SID4, SEED, VERIFY_SEED = 1346, 1346, 260000 + 1346
PORT = 8000 + SID4 % 900                      # 8446
BASE = f"http://127.0.0.1:{PORT}"
MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
MODEL = "qwen2.5:3b via Ollama (temperature 0, seed 1346); embeddings BAAI/bge-small-en-v1.5"
SUMMARIZE_EVERY = int(os.getenv("SUMMARIZE_EVERY_USER_MSGS", "4"))
checks = []


def check(name, passed, detail=""):
    checks.append({"name": name, "passed": bool(passed), "detail": str(detail)[:240]})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))


def safe(name, fn):
    try:
        fn()
    except Exception as e:                                       # noqa: BLE001
        check(name, False, f"{e.__class__.__name__}: {e}")


def git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=REPO, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:                                            # noqa: BLE001
        return "UNKNOWN"


print(f"Running HW6 smoke tests (PORT_BASE={PORT}, VERIFY_SEED={VERIFY_SEED}) ...")
s = requests.Session()
J = {"Content-Type": "application/json"}


# ---- Part 1: backend + MongoDB document API ------------------------------------
def c_health():
    r = s.get(f"{BASE}/health", timeout=5).json()
    check("backend_responds_on_port_base", r.get("port") == PORT, r)
    check("backend_reaches_mongodb", r.get("mongo") == "ok", r.get("mongo"))


def c_collections():
    from pymongo import MongoClient
    db = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)["s1346_doc"]
    names = set(db.list_collection_names())
    need = {"incident_reports", "messages", "summaries", "episodes"}
    check("mongo_collections_exist", need <= names, sorted(names & need))
    opts = {c["name"]: c.get("options", {}) for c in db.list_collections()}
    with_validator = sorted(n for n in need if "$jsonSchema" in opts.get(n, {}).get("validator", {}))
    check("collections_have_jsonschema_validator", set(with_validator) == need, with_validator)
    from pymongo.errors import WriteError
    try:     # the database itself must reject an invalid document (Pydantic bypassed)
        db["incident_reports"].insert_one({"title": "x" * 150, "status": "Done", "category": "Flood"})
        db["incident_reports"].delete_many({"status": "Done", "category": "Flood"})
        check("mongo_validator_rejects_invalid_document", False, "invalid document was accepted")
    except WriteError as e:
        check("mongo_validator_rejects_invalid_document", e.code == 121, f"WriteError code {e.code}")


def c_crud():
    url = f"{BASE}/api/doc/incidents"
    body = {"title": f"verify-hw06 {VERIFY_SEED}", "description": "smoke test record", "location": "Verify St",
            "category": "Delay", "occurred_at": "2026-10-01T08:00:00Z"}
    r = s.post(url, json=body, timeout=5)
    created = r.json() if r.status_code == 201 else {}
    doc_id = created.get("id")
    check("doc_create_201_with_defaults_and_timestamps",
          r.status_code == 201 and created.get("status") == "Reported" and created.get("created_at"),
          f"status={r.status_code}")
    listed = s.get(url, params={"limit": 200}, timeout=5)
    check("doc_list_200_contains_record", listed.status_code == 200 and any(d["id"] == doc_id for d in listed.json()),
          f"{len(listed.json())} docs")
    got = s.get(f"{url}/{doc_id}", timeout=5)
    check("doc_get_by_id_200", got.status_code == 200 and got.json()["title"] == body["title"])
    time.sleep(0.01)
    up = s.put(f"{url}/{doc_id}", json={"status": "Resolved"}, timeout=5)
    check("doc_update_200_refreshes_updated_at", up.status_code == 200 and up.json()["status"] == "Resolved"
          and up.json()["updated_at"] > up.json()["created_at"], f"status={up.status_code}")
    gone = s.delete(f"{url}/{doc_id}", timeout=5).status_code
    after = s.get(f"{url}/{doc_id}", timeout=5).status_code
    check("doc_delete_200_then_get_404", gone == 200 and after == 404, f"delete={gone} get={after}")


def c_validation():
    url = f"{BASE}/api/doc/incidents"
    good = {"title": "t", "category": "Delay", "occurred_at": "2026-10-01T08:00:00Z"}
    cases = {
        "missing_required": ({"description": "no title"}, 422),
        "invalid_enum": ({**good, "category": "Flood"}, 422),
        "wrong_type": ({**good, "title": 123}, 422),
        "title_over_100": ({**good, "title": "x" * 101}, 422),
        "bad_date": ({**good, "occurred_at": "yesterday"}, 422),
    }
    got = {k: s.post(url, json=b, timeout=5) for k, (b, _) in cases.items()}
    ok = all(got[k].status_code == code and got[k].json().get("detail") for k, (_, code) in cases.items())
    check("doc_invalid_data_422_with_messages", ok, {k: v.status_code for k, v in got.items()})
    codes = {"bad_id": s.get(f"{url}/not-an-id", timeout=5).status_code,
             "unknown_id": s.get(f"{url}/{'0' * 24}", timeout=5).status_code,
             "non_json": s.post(url, data="title=x", headers={"Content-Type": "text/plain"}, timeout=5).status_code}
    check("doc_error_codes_400_404_415", codes == {"bad_id": 400, "unknown_id": 404, "non_json": 415}, codes)


for n, f in [("health", c_health), ("collections", c_collections), ("crud", c_crud), ("validation", c_validation)]:
    safe(n, f)


# ---- Part 2: memory endpoints -------------------------------------------------------
def c_chat():
    user = f"verify-hw06-{int(time.time())}"
    session, results = None, []
    msgs = ["Hi, my name is Riley and I dispatch the Route 99 night buses.",
            "Bus 9901 has a flat tyre at Elm St & 2nd St.",
            "What category is a flat tyre?",
            "What is my name?"][:max(SUMMARIZE_EVERY, 2)]
    try:
        for m in msgs:
            r = s.post(f"{BASE}/api/chat", json={"user_id": user, "session_id": session, "message": m}
                       if session else {"user_id": user, "message": m}, timeout=600)
            r.raise_for_status()
            results.append(r.json())
            session = results[-1]["session_id"]
        first, last = results[0], results[-1]
        check("chat_returns_reply", all(isinstance(x["reply"], str) and x["reply"].strip() for x in results),
              f"{len(results)} replies, session={session}")
        mu = last["memory_used"]
        check("chat_reports_memory_used", {"short_term", "long_term", "episodic"} <= set(mu)
              and mu["short_term"]["count"] == min(2 * (len(msgs) - 1), mu["short_term"]["n"]),
              f"window={mu['short_term']['count']} n={mu['short_term']['n']}")
        u = last["usage"]
        check("chat_logs_token_components",
              u["prompt_tokens_full"] > 0 and u["completion_tokens"] > 0 and u["tokens_system_primer"] > 0
              and u["tokens_short_term_window"] > 0 and u["latency_ms"] > 0,
              f"prompt_full={u['prompt_tokens_full']} completion={u['completion_tokens']}")
        check("summary_triggered_every_m_user_messages",
              last["memory_updates"]["session_summary_updated"] and not first["memory_updates"]["session_summary_updated"],
              f"M={SUMMARIZE_EVERY}")
        mem = s.get(f"{BASE}/api/memory/{user}", timeout=10).json()
        check("memory_endpoint_shape",
              len(mem["recent_messages"]) == 2 * len(msgs) and mem["latest_session_summary"] is not None
              and isinstance(mem["recent_episodes"], list),
              f"messages={len(mem['recent_messages'])} episodes={len(mem['recent_episodes'])}")
        check("episodic_facts_stored_with_embeddings",
              len(mem["recent_episodes"]) >= 1 and all(e["embedding_dim"] > 0 and 0 <= e["importance"] <= 1
                                                       for e in mem["recent_episodes"]),
              [e["fact"] for e in mem["recent_episodes"]][:3])
        agg = s.get(f"{BASE}/api/aggregate/{user}", timeout=10).json()
        check("aggregate_daily_counts", agg["total_messages"] == 2 * len(msgs)
              and all({"date", "messages"} <= set(d) for d in agg["daily_message_counts"])
              and len(agg["recent_summaries"]) >= 1, agg["daily_message_counts"])
    finally:
        s.delete(f"{BASE}/api/memory/{user}", timeout=10)        # remove the temporary user


safe("chat", c_chat)


# ---- Part 3: experiment artifacts ---------------------------------------------------
def c_probes():
    p = yaml.safe_load((HW / "memory_probes.yaml").read_text())
    check("memory_probes_yaml_5_probes_rubric_1_to_5",
          len(p["probes"]) == 5 and set(p["rubric"]) == {1, 2, 3, 4, 5}
          and all(q.get("question") and q.get("expected") and q.get("required") for q in p["probes"]))


def c_sweep():
    rows = list(csv.DictReader(open(RAW / "memory_turns.csv")))
    per = {k: sum(1 for r in rows if r["setting"] == k and r["phase"] == "conversation")
           for k in ("n4", "n12", "n30", "policy")}
    check("sweep_30_turns_per_setting", set(per.values()) == {30}, per)
    windows = {k: max(int(r["short_term_count"]) for r in rows if r["setting"] == k) for k in per}
    check("window_respects_short_term_n", windows["n4"] <= 4 and windows["n12"] <= 12 and windows["n30"] <= 30,
          windows)
    probes = list(csv.DictReader(open(RAW / "probe_scores.csv")))
    check("probe_scores_20_rows_in_range", len(probes) == 20 and all(1 <= int(p["score"]) <= 5 for p in probes),
          len(probes))
    summary = json.loads((RAW / "memory_summary.json").read_text())
    pol, base = summary["policy"], summary["n30"]
    check("policy_reduces_prompt_tokens",
          pol["mean_prompt_tokens_full"] < base["mean_prompt_tokens_full"],
          f"{base['mean_prompt_tokens_full']} -> {pol['mean_prompt_tokens_full']}")
    check("cost_estimate_present", (RAW / "memory_cost.json").exists())


for n, f in [("probes", c_probes), ("sweep", c_sweep)]:
    safe(n, f)


# ---- Part 4: file-based memory -------------------------------------------------------
def c_agent_md():
    text = (REPO / "AGENT.md").read_text()
    sections, current, count = set(), None, 0
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip().lower()
        elif re.match(r"^- [A-Z]\d+\. ", line) and current:
            sections.add(current)
            count += 1
    categories = {"project description", "technology stack", "coding conventions", "testing approach",
                  "prohibited actions"}
    covered = sorted(c for c in categories if any(s.startswith(c) for s in sections))
    check("agent_md_5_instructions_3_categories", count >= 5 and len(covered) >= 3,
          f"{count} instructions, categories={covered}")


def c_consolidation():
    import file_memory as fm
    original = HW / "memory_test" / "MEMORY_original.md"
    text = original.read_text()
    check("original_memory_55_lines_needs_consolidation",
          len(text.splitlines()) == 55 and fm.needs_consolidation(text), fm.consolidation_reasons(text))
    tmp = Path(tempfile.mkdtemp()) / "MEMORY.md"
    shutil.copyfile(original, tmp)
    report = fm.consolidate_file(tmp)
    result = tmp.read_text()
    facts = fm.parse_memory(result).facts
    superseded = result.split("## Superseded", 1)[-1]
    kept_all = all(o["text"] in superseded for c in report["contradictions"] for o in c["superseded"])
    check("consolidation_under_40_lines_dups_merged",
          report["lines_after"] < 40 and len({f.topic for f in facts}) == len(facts)
          and len(report["duplicates_merged"]) >= 3, f"{report['lines_before']} -> {report['lines_after']} lines")
    check("contradictions_resolved_explicitly_none_lost",
          len(report["contradictions"]) >= 3 and kept_all, f"{len(report['contradictions'])} contradictions")
    committed = HW / "memory_test" / "MEMORY_consolidated.md"
    check("consolidated_memory_committed", committed.exists() and len(committed.read_text().splitlines()) < 40)
    shutil.rmtree(tmp.parent, ignore_errors=True)


def c_generated():
    rep = json.loads((RAW / "agent_md_check.json").read_text())
    gen = next(t for t in rep["targets"] if t["kind"] == "model-generated")
    beh = gen.get("behaviour", {})
    check("generated_function_follows_agent_md", all(r["passed"] for r in gen["static"]),
          [r["rule"] for r in gen["static"] if not r["passed"]] or "all static rules pass")
    check("generated_function_behaviour", "error" not in beh and all(beh.values()), beh)


def c_ollama():
    names = [m["name"] for m in requests.get("http://localhost:11434/api/tags", timeout=5).json()["models"]]
    check("ollama_model_available", "qwen2.5:3b" in names, names)


for n, f in [("agent_md", c_agent_md), ("consolidation", c_consolidation),
             ("generated_function", c_generated), ("ollama", c_ollama)]:
    safe(n, f)

report = {
    "homework": "HW6",
    "sid4": SID4,
    "commit_hash": git("rev-parse", "HEAD"),
    "tag_hw6_commit": git("rev-list", "-n", "1", "hw6"),
    "model_configuration": MODEL,
    "seed": SEED,
    "verify_seed": VERIFY_SEED,
    "port_base": PORT,
    "timestamp": datetime.now().isoformat(timespec="seconds"),
    "checks": checks,
    "summary": f"{sum(c['passed'] for c in checks)}/{len(checks)} passed",
    "all_passed": all(c["passed"] for c in checks),
}
out = HW / "verification.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2))
print(f"\n{report['summary']}  ->  {out.relative_to(REPO)}")
