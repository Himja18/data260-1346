"""DATA-260 HW6 offline test suite - no MongoDB server, Ollama or network needed.

    python code/test_hw06.py        (or: make hw06-test)

MongoDB is replaced by mongomock, the model by FakeClient, embeddings by the hashed
bag-of-words embedder (AGENT.md rule X1). Last line: "<passed>/<total> passed".
"""
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.update({"MONGO_MOCK": "1", "EMBED_BACKEND": "hash", "TOKENIZER_NAME": "none",
                   "DATABASE_URL": "sqlite://", "MEMORY_USAGE_LOG": os.devnull})
REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "code"), str(REPO / "code" / "backend"), str(REPO / "src")]

import mongomock  # noqa: E402

import file_memory as fm  # noqa: E402
import memory_logic as ml  # noqa: E402
from agent_md_check import check_source  # noqa: E402
from chat import ChatRequest, handle_chat  # noqa: E402
from embeddings import HashEmbedder  # noqa: E402
from memory_store import MemoryStore  # noqa: E402
from run_memory_experiment import score_probe  # noqa: E402

RESULTS = []


@dataclass
class FakeResult:
    content: str
    input_tokens: int = 10
    output_tokens: int = 5
    total_tokens: int = 15
    latency_ms: float = 1.0


class FakeClient:
    """Deterministic stand-in for ModelClient."""

    def __init__(self) -> None:
        self.calls = []

    def complete(self, messages: list, tools=None, options=None) -> FakeResult:
        self.calls.append(messages)
        last = messages[-1]["content"]
        if last.startswith("Extract up to"):
            msg = last.split("MESSAGE:\n", 1)[1]
            if "name is" in msg:
                return FakeResult('{"facts": [{"fact": "The user\'s name is Dana.", "importance": 1.4},'
                                  ' {"fact": "The user is a dispatcher.", "importance": 0.7}]}')
            return FakeResult('{"facts": []}')
        if last.startswith("Update the running summary"):
            return FakeResult("- session summary")
        if last.startswith("Condense these"):
            return FakeResult("- lifetime summary")
        return FakeResult(f"reply to: {last[:40]}")


def test(fn):
    """Register and run one test."""
    try:
        fn()
        RESULTS.append((fn.__name__, True, ""))
    except Exception as exc:                                     # noqa: BLE001
        RESULTS.append((fn.__name__, False, f"{exc.__class__.__name__}: {exc}"))
    return fn


# ---- memory logic ----------------------------------------------------------------------
@test
def window_policy_compresses_only_old_assistant_turns():
    window = [{"role": "user", "content": "My bus is 4471."},
              {"role": "assistant", "content": "Noted. " + "Long explanation. " * 30},
              {"role": "user", "content": "ok"}, {"role": "assistant", "content": "Sure. More text here."},
              {"role": "user", "content": "next"}, {"role": "assistant", "content": "Recent reply. Kept."}]
    out = ml.apply_window_policy(window, "compress_assistant", keep_recent=4, max_chars=120)
    assert out[0]["content"] == "My bus is 4471."
    assert out[1]["content"] == "Noted."
    assert out[5]["content"] == "Recent reply. Kept."
    assert ml.apply_window_policy(window, "none") == [{"role": m["role"], "content": m["content"]} for m in window]


@test
def parse_facts_validates_and_limits():
    reply = '```json\n{"facts": [{"fact": "A", "importance": 2}, {"fact": "", "importance": 0.5},' \
            '{"fact": "B", "importance": "x"}, {"fact": "C", "importance": -1}, {"fact": "D", "importance": 0.3}]}\n```'
    facts = ml.parse_facts(reply)
    assert [f["fact"] for f in facts] == ["A", "B", "C"]
    assert [f["importance"] for f in facts] == [1.0, 0.5, 0.0]
    assert ml.parse_facts("no json here") == []


@test
def retrieval_ranks_by_cosine_and_applies_floor():
    emb = HashEmbedder()
    episodes = [{"fact": f, "importance": 0.5, "session_id": "s", "created_at": None,
                 "embedding": emb.embed([f])[0]}
                for f in ["bus 4471 broke down at santa clara", "the user likes tea", "route 23 assignment"]]
    hits = ml.retrieve_episodes(emb.embed(["which bus broke down at santa clara"])[0], episodes, 2, 0.1)
    assert hits[0]["fact"].startswith("bus 4471")
    assert all(h["score"] >= 0.1 for h in hits)


@test
def summary_triggers():
    assert [n for n in range(1, 13) if ml.should_summarize(n, 4)] == [4, 8, 12]
    assert not ml.should_summarize(0, 4) and not ml.should_condense_lifetime(1, 2)
    assert ml.should_condense_lifetime(2, 2)


@test
def prompt_order_matches_brief():
    msgs, parts = ml.build_prompt("- session", "- lifetime", [{"role": "user", "content": "earlier"},
                                                              {"role": "assistant", "content": "ok"}],
                                  "current?", [{"fact": "Fact one."}])
    assert msgs[0]["role"] == "system" and "- lifetime" in msgs[0]["content"] and "- session" in msgs[0]["content"]
    assert msgs[1]["content"] == "earlier" and msgs[2]["content"] == "ok"
    assert msgs[-1]["content"].startswith("current?") and msgs[-1]["content"].endswith("- Fact one.")
    assert parts["episodic_facts"] and parts["long_term_summary"]


# ---- chat orchestration with mongomock ------------------------------------------------------
def _store() -> MemoryStore:
    return MemoryStore(mongomock.MongoClient(tz_aware=True)["s1346_doc"])


@test
def chat_flow_window_summaries_episodes():
    store, client, emb = _store(), FakeClient(), HashEmbedder()
    session, bodies = None, []
    for i in range(8):
        msg = "Hi, my name is Dana and I dispatch buses." if i == 0 else f"question {i}"
        body = handle_chat(ChatRequest(user_id="u1", session_id=session, message=msg, short_term_n=4),
                           store, client, emb)
        session = body["session_id"]
        bodies.append(body)
    assert [b["memory_used"]["short_term"]["count"] for b in bodies] == [0, 2, 4, 4, 4, 4, 4, 4]
    assert [b["memory_updates"]["session_summary_updated"] for b in bodies] == [False] * 3 + [True] + [False] * 3 + [True]
    assert bodies[7]["memory_updates"]["lifetime_summary_updated"]          # 2nd session summary
    assert bodies[4]["memory_used"]["long_term"]["session_summary"] == "- session summary"
    assert len(bodies[0]["memory_updates"]["episodes_stored"]) == 2
    assert bodies[0]["memory_updates"]["episodes_stored"][0]["importance"] == 1.0
    assert store.messages.count_documents({"user_id": "u1"}) == 16
    assert all(k in bodies[-1]["usage"] for k in ("prompt_tokens_full", "tokens_short_term_window",
                                                  "tokens_episodic_facts", "latency_ms"))


@test
def episodes_dedup_and_memory_views():
    store, client, emb = _store(), FakeClient(), HashEmbedder()
    first = handle_chat(ChatRequest(user_id="u2", message="my name is Dana"), store, client, emb)
    handle_chat(ChatRequest(user_id="u2", session_id=first["session_id"], message="my name is Dana"),
                store, client, emb)
    assert store.episodes.count_documents({"user_id": "u2"}) == 2       # second identical pair deduped
    assert store.recent_episodes("u2")[0]["embedding_dim"] == 256
    daily = store.daily_message_counts("u2")
    assert daily[0]["messages"] == 4 and daily[0]["user_messages"] == 2
    assert store.delete_user("u2")["messages"] == 4


# ---- Part 1 API (FastAPI TestClient; skipped if httpx is missing) ----------------------------
@test
def doc_api_crud_and_validation():
    try:
        from fastapi.testclient import TestClient
    except Exception:                                            # noqa: BLE001
        return                                                   # httpx not installed - nothing to test
    import main
    c = TestClient(main.app)
    url = "/api/doc/incidents"
    r = c.post(url, json={"title": "t", "category": "Delay", "occurred_at": "2026-10-01T08:00:00Z"})
    assert r.status_code == 201 and r.json()["status"] == "Reported"
    doc_id = r.json()["id"]
    assert c.put(f"{url}/{doc_id}", json={"status": "Closed"}).json()["status"] == "Closed"
    assert c.post(url, json={"title": "t", "category": "Flood", "occurred_at": "2026-10-01"}).status_code == 422
    assert c.post(url, json={"category": "Delay"}).json()["error"] == "validation_error"
    assert c.get(f"{url}/xyz").status_code == 400
    assert c.delete(f"{url}/{doc_id}").status_code == 200
    assert c.get(f"{url}/{doc_id}").status_code == 404


# ---- Part 4 file memory -----------------------------------------------------------------------
@test
def consolidation_rules():
    text = (REPO / "reports" / "hw06" / "memory_test" / "MEMORY_original.md").read_text()
    assert fm.needs_consolidation(text)
    fresh = "<!-- last_consolidated: %s -->\n- [2026-10-01] (a) x\n" % datetime.now(timezone.utc).isoformat()
    assert not fm.needs_consolidation(fresh)
    old = fresh.replace(datetime.now(timezone.utc).isoformat()[:10],
                        (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()[:10])
    assert fm.needs_consolidation(old)
    new, rep = fm.consolidate_text(text)
    assert rep["lines_after"] < 40 and len(rep["contradictions"]) == 5
    again, rep2 = fm.consolidate_text(new)                       # idempotent
    assert rep2["facts_after"] == rep["facts_after"] and not rep2["contradictions"]
    assert again.split("## Facts")[1] == new.split("## Facts")[1]


@test
def dream_append_reasserts_older_value():
    tmp = Path(tempfile.mkdtemp()) / "M.md"
    shutil.copyfile(REPO / "reports" / "hw06" / "memory_test" / "MEMORY_original.md", tmp)
    added = fm.append_facts(tmp, [("project.port", "The backend runs on port 8446 (PORT_BASE)."),
                                  ("project.mongo", "Document data and chat memory live in MongoDB database s1346_doc.")],
                            today="2026-10-17")
    assert len(added) == 1 and "8446" in added[0]                # mongo fact is already current
    fm.consolidate_file(tmp)
    current = {f.topic: f.text for f in fm.parse_memory(tmp.read_text()).facts}
    assert "8446" in current["project.port"]
    shutil.rmtree(tmp.parent)


@test
def system_prompt_contains_both_files_without_superseded():
    prompt = fm.build_system_prompt("BASE", "## Rules\n- C1. snake_case", "## Facts\n- [2026-01-01] (a) new\n"
                                    "## Superseded\n- [2025-01-01] (a) old")
    assert "C1. snake_case" in prompt and "(a) new" in prompt and "(a) old" not in prompt


@test
def probe_rubric():
    probe = {"required": [["\\blena\\b"]], "forbidden": ["\\bmarco\\b"]}
    unknown = ["(don't|do not) know"]
    assert score_probe("Lena Park.", probe, unknown)[0] == 5
    assert score_probe("Lena Park replaced Marco.", probe, unknown)[0] == 4
    assert score_probe("I don't know.", probe, unknown)[0] == 2
    assert score_probe("Marco Reyes.", probe, unknown)[0] == 1
    two = {"required": [["4471"], ["santa clara"]], "forbidden": []}
    assert score_probe("Bus 4471.", two, unknown)[0] == 3


@test
def handwritten_code_follows_agent_md():
    code = (REPO / "code" / "file_memory.py").read_text()
    assert all(r["passed"] for r in check_source(code))


if __name__ == "__main__":
    for name, ok, detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    print(f"{sum(ok for _, ok, _ in RESULTS)}/{len(RESULTS)} passed")
