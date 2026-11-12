"""HW10 Part 1 - Streamlit operations dashboard for the s1346 cache + Kafka agent pipeline.

    streamlit run code/hw10/dashboard.py --server.port 8448

Pages: Summary (traffic, cache hits vs misses, errors, latency) | Evaluation (Part 2 scores, Part 3 judge
validation) | Trace lookup (one request's journey by trace_id).
Data sources (all written by the system itself, nothing is typed in by hand):
    reports/hw10/spans.jsonl           spans from the cache ingress, Planner, Writer, Reviewer, evaluator
    reports/hw10/eval_results.jsonl    evaluator output (Part 2)
    reports/hw10/judge_validation.json judge vs human labels + repeatability (Part 3)
    reports/hw10/latency_experiment.json  50 cache-miss stage latencies (Part 4.3)
    reports/hw10/trace_examples.json   the three required trace ids (Part 4.2)
"""
import json
import sys
import time
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hw10_config as cfg  # noqa: E402
from tracing import SPANS_FILE  # noqa: E402

STAGE_ORDER = ["request", "cache_lookup", "queue_inbox", "planner", "queue_tasks", "writer", "queue_drafts",
               "reviewer", "queue_final", "evaluation"]
WINDOWS = {"Last 1 hour": 3600, "Last 24 hours": 86400, "Last 7 days": 7 * 86400, "All data": None}

st.set_page_config(page_title=f"{cfg.PREFIX} operations", layout="wide")


# ------------------------------------------------------------------ data loading (cached)
@st.cache_data(ttl=15, show_spinner=False)
def load_jsonl(path: str, mtime: float) -> pd.DataFrame:  # noqa: ARG001 - mtime busts the cache when the file changes
    """JSON lines -> DataFrame (bad lines skipped). Cached: re-read only when the file changed or after 15 s."""
    rows = []
    p = Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return pd.DataFrame(rows)


@st.cache_data(ttl=60, show_spinner=False)
def load_json(path: str, mtime: float) -> dict:  # noqa: ARG001
    """A JSON file or {}."""
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@st.cache_resource(show_spinner=False)
def redis_client():  # noqa: ANN201
    """One Redis connection for the whole app (a reusable resource, not data)."""
    import redis
    return redis.Redis.from_url(cfg.cfg9.REDIS_URL, socket_timeout=1)


def mtime(p: Path) -> float:
    return p.stat().st_mtime if p.exists() else 0.0


def spans() -> pd.DataFrame:
    return load_jsonl(str(SPANS_FILE), mtime(SPANS_FILE))


def evals() -> pd.DataFrame:
    return load_jsonl(str(cfg.EVAL_RESULTS), mtime(cfg.EVAL_RESULTS))


def jfile(p: Path) -> dict:
    return load_json(str(p), mtime(p))


def p(values: pd.Series, q: float) -> float:
    return float(values.quantile(q / 100)) if len(values) else float("nan")


def source_note(window: str, source: str) -> None:
    st.caption(f"Window: **{window}** · Source: `{source}`")


# ------------------------------------------------------------------ pages
def page_summary() -> None:
    st.header("Summary")
    window = st.radio("Time window", list(WINDOWS), index=1, horizontal=True)
    df = spans()
    if df.empty:
        st.warning(f"No spans yet in {SPANS_FILE}.")
        return
    secs = WINDOWS[window]
    cutoff_ms = (time.time() - secs) * 1000 if secs else 0
    req = df[(df["stage"] == "request") & (df["start_ms"] >= cutoff_ms)].copy()
    look = df[(df["stage"] == "cache_lookup") & (df["start_ms"] >= cutoff_ms)]
    src_req = "reports/hw10/spans.jsonl - stage=request (root span, cache ingress)"
    n = len(req)
    hits = int((look["status"] == "hit").sum())
    misses = int((look["status"] == "miss").sum())
    errors = int((req["status"] == "error").sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Requests", n)
    c2.metric("Cache hits", hits)
    c3.metric("Cache misses", misses)
    c4.metric("Cache hit rate", f"{100 * hits / max(hits + misses, 1):.1f}%")
    st.caption(f"Window: **{window}** · Requests from `{src_req}`; hits/misses from "
               "`spans.jsonl - stage=cache_lookup, status hit|miss`. Hit rate = hits / (hits + misses).")

    miss_lat = req[(req.get("cache") == "miss") & (req["status"] == "ok")]["duration_ms"] if "cache" in req else pd.Series(dtype=float)
    hit_lat = req[(req.get("cache") == "hit")]["duration_ms"] if "cache" in req else pd.Series(dtype=float)
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Error rate", f"{100 * errors / max(n, 1):.1f}%", help="requests whose root span has status=error")
    d2.metric("Cache-miss latency p50 / p95", f"{p(miss_lat, 50) / 1000:.1f} s / {p(miss_lat, 95) / 1000:.1f} s")
    d3.metric("Cache-hit latency p50 / p95", f"{p(hit_lat, 50):.0f} ms / {p(hit_lat, 95):.0f} ms")
    ev = df[(df["stage"] == "evaluation") & (df["start_ms"] >= cutoff_ms)]
    d4.metric("Evaluations ok / error", f"{int((ev['status'] == 'ok').sum())} / {int((ev['status'] == 'error').sum())}")
    st.caption(f"Window: **{window}** · Error rate = request spans with status=error / all request spans. "
               "End-to-end latency = duration of the root `request` span (question in -> answer out), shown separately "
               "for cache misses (successful) and cache hits. Evaluations from `spans.jsonl - stage=evaluation`.")

    try:
        keys = sum(1 for _ in redis_client().scan_iter(match=f"{cfg.PREFIX}:semcache:*", count=500))
        st.caption(f"Live Redis: {keys} cached answers under `{cfg.PREFIX}:semcache:*` (connection via @st.cache_resource)")
    except Exception as exc:  # noqa: BLE001
        st.caption(f"Live Redis not reachable ({exc.__class__.__name__}) - the metrics above come from the span log.")

    if n:
        req["time"] = pd.to_datetime(req["start_ms"], unit="ms", utc=True).dt.tz_convert("America/Los_Angeles")
        req["path"] = req.apply(lambda r: "error" if r["status"] == "error" else f"cache {r.get('cache', '?')}", axis=1)
        req["seconds"] = req["duration_ms"] / 1000
        color = alt.Scale(domain=["cache hit", "cache miss", "error"], range=["#2e7d32", "#ef6c00", "#c62828"])
        chart = alt.Chart(req).mark_circle(size=60).encode(
            x=alt.X("time:T", title="request start"), y=alt.Y("seconds:Q", title="end-to-end latency (s)"),
            color=alt.Color("path:N", scale=color, title="path"),
            tooltip=["trace_id", "path", "duration_ms", "query"]).properties(height=280)
        st.altair_chart(chart, width="stretch")
        st.caption(f"Window: **{window}** · Source: `{src_req}`")

    lat = jfile(cfg.LATENCY_RESULTS)
    if lat:
        st.subheader("Stage latency - 50 confirmed cache misses (Part 4.3)")
        t = pd.DataFrame(lat["stages"])[["stage", "p50", "p95", "pct_of_e2e"]]
        t.columns = ["Stage", "p50 (ms)", "p95 (ms)", "% of cache-miss end-to-end"]
        st.dataframe(t, hide_index=True, width="stretch")
        hit = lat.get("cache_hit_ms") or {}
        st.caption(f"Source: `reports/hw10/latency_experiment.json` ({lat['n_complete']} traces). End-to-end p50 "
                   f"{lat['end_to_end_ms']['p50'] / 1000:.1f} s, p95 {lat['end_to_end_ms']['p95'] / 1000:.1f} s. "
                   f"Cache-hit latency kept separate: p50 {hit.get('p50', '-')} ms, p95 {hit.get('p95', '-')} ms.")


def page_evaluation() -> None:
    st.header("Evaluation")
    st.subheader("Part 2 - pipeline evaluation (GEval, 1-5)")
    ev = evals()
    if ev.empty:
        st.info("No evaluations yet - run evaluator.py and send a question.")
    else:
        ok = ev[ev["status"] == "ok"].copy()
        rows = []
        for _, r in ok.iterrows():
            rows.append({"trace_id": r["trace_id"], "question": str(r["inputs"]["question"]).split("\n")[0][:80],
                         "Plan": r["plan_quality"]["score"], "Writer draft": r["writer_helpfulness"]["score"],
                         "Final answer": r["final_helpfulness"]["score"],
                         "Draft (final metric)": r["improvement"]["draft_score"],
                         "Final - draft": r["improvement"]["difference"],
                         "Reviewer": r["inputs"]["reviewer_status"], "evaluated_at": r["evaluated_at"]})
        table = pd.DataFrame(rows)
        st.dataframe(table, hide_index=True, width="stretch")
        st.caption(f"Source: `reports/hw10/eval_results.jsonl` - {len(ok)} evaluated traces, "
                   f"{int((ev['status'] == 'error').sum())} evaluation errors.")
        if len(table):
            means = pd.DataFrame({"stage": ["Planner (plan quality)", "Writer (draft helpfulness)",
                                            "Reviewer (final helpfulness)"],
                                  "mean score": [table["Plan"].mean(), table["Writer draft"].mean(),
                                                 table["Final answer"].mean()]})
            st.altair_chart(alt.Chart(means).mark_bar().encode(
                x=alt.X("mean score:Q", scale=alt.Scale(domain=[0, 5])), y=alt.Y("stage:N", sort=None))
                .properties(height=150), width="stretch")
            pick = st.selectbox("Inspect one evaluated case", table["trace_id"].tolist())
            r = ok[ok["trace_id"] == pick].iloc[0]
            c1, c2 = st.columns(2)
            c1.markdown("**Question**")
            c1.code(r["inputs"]["question"], language=None)
            c1.markdown(f"**Plan** - score {r['plan_quality']['score']}: _{r['plan_quality']['reason']}_")
            c1.markdown("\n".join(f"{i}. {step}" for i, step in enumerate(r["inputs"]["plan"], 1)))
            c2.markdown(f"**Writer draft** - score {r['writer_helpfulness']['score']}: _{r['writer_helpfulness']['reason']}_")
            c2.write(r["inputs"]["draft"])
            c2.markdown(f"**Final answer** ({r['inputs']['reviewer_status']}) - score "
                        f"{r['final_helpfulness']['score']}: _{r['final_helpfulness']['reason']}_")
            c2.write(r["inputs"]["final_answer"])
            st.info(f"Final vs draft: {r['improvement']['draft_score']} -> {r['improvement']['final_score']} "
                    f"(difference {r['improvement']['difference']}). {r['improvement']['interpretation']}")

    st.subheader("Part 3 - is the judge trustworthy?")
    jv = jfile(cfg.JUDGE_VALIDATION)
    if not jv:
        st.info("Run run_judge_validation.py after committing eval_cases.json and human_labels.csv.")
    else:
        s, rep = jv["summary"], jv["summary"]["repeatability"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Spearman rho (human vs judge)", f"{s['spearman_run1']:.3f}")
        c2.metric("Mean absolute difference", f"{s['mad_run1']:.2f}")
        c3.metric("Cases whose score changed (3 runs)", f"{rep['cases_with_any_change']}/{s['n_scored_all_runs']}")
        c4.metric("Mean / max |change|", f"{rep['mean_abs_change']:.2f} / {rep['max_abs_change']}")
        st.caption(f"Source: `reports/hw10/judge_validation.json` - {s['n_cases']} frozen drafts, human labels committed "
                   f"before judging ({jv['labels_frozen'][1]['last_commit']}). Judge: {jv['settings']['judge_model']}, "
                   f"temperature {jv['settings']['temperature']}, 3 runs.")
        cases = pd.DataFrame([{"case": c["case_id"], "type": c["question_type"], "human": c["human"],
                               "run 1": c["judge"][0], "run 2": c["judge"][1], "run 3": c["judge"][2]}
                              for c in jv["cases"]])
        left, right = st.columns([3, 2])
        left.dataframe(cases, hide_index=True, width="stretch", height=420)
        right.altair_chart(alt.Chart(cases).mark_circle(size=90, opacity=0.6).encode(
            x=alt.X("human:Q", scale=alt.Scale(domain=[0.5, 5.5]), title="human label"),
            y=alt.Y("run 1:Q", scale=alt.Scale(domain=[0.5, 5.5]), title="judge score (run 1)"),
            tooltip=["case", "human", "run 1"]).properties(height=380), width="stretch")

    st.subheader("What the scores suggest about Planner / Writer / Reviewer coordination")
    if cfg.INTERPRETATION.exists():
        st.markdown(cfg.INTERPRETATION.read_text(encoding="utf-8"))
    else:
        st.caption("reports/hw10/interpretation.md not written yet.")


def page_trace() -> None:
    st.header("Trace lookup")
    ex = jfile(cfg.TRACE_EXAMPLES)
    options = {"(type a trace_id)": ""} | {f"{k.replace('_', ' ')}: {v['trace_id']}": v["trace_id"] for k, v in ex.items()}
    pick = st.selectbox("Saved examples (Part 4.2)", list(options))
    trace_id = st.text_input("trace_id", value=options[pick]).strip()
    if not trace_id:
        return
    df = spans()
    t = df[df["trace_id"] == trace_id].copy() if not df.empty else pd.DataFrame()
    if t.empty:
        st.error(f"No spans for trace_id {trace_id}")
        return
    t["order"] = t["stage"].map(lambda s: STAGE_ORDER.index(s) if s in STAGE_ORDER else 99)
    t = t.sort_values(["start_ms", "order"])
    lookup = t[t["stage"] == "cache_lookup"]
    failed = (t["status"] == "error").any()
    path = lookup["status"].iloc[0] if len(lookup) else "?"
    if failed:
        bad = t[(t["status"] == "error") & (~t["stage"].isin(["request", "evaluation"]))]
        where = bad["stage"].iloc[0] if len(bad) else t[t["status"] == "error"]["stage"].iloc[0]
        st.error(f"FAILED trace - cache {path.upper()}, failing stage: **{where}**")
    elif path == "hit":
        st.success("CACHE HIT - answered from Redis; no Kafka or agent spans")
    else:
        st.warning("CACHE MISS - full agent path: inbox -> Planner -> Writer -> Reviewer -> final -> evaluation")
    root = t[t["stage"] == "request"]
    if len(root):
        st.caption(f"Question: {root['query'].iloc[0]} · end-to-end {root['duration_ms'].iloc[0]:.0f} ms")
    cols = ["stage", "component", "start", "end", "duration_ms", "status"] + (["error"] if "error" in t else [])
    st.dataframe(t[cols].fillna(""), hide_index=True, width="stretch")
    base = t["start_ms"].min()
    t["from_ms"] = t["start_ms"] - base
    t["to_ms"] = t["end_ms"] - base
    scale = alt.Scale(domain=["ok", "hit", "miss", "error"], range=["#1565c0", "#2e7d32", "#ef6c00", "#c62828"])
    st.altair_chart(alt.Chart(t).mark_bar(height=14).encode(
        x=alt.X("from_ms:Q", title="ms since the request started"), x2="to_ms:Q",
        y=alt.Y("stage:N", sort=list(t["stage"])), color=alt.Color("status:N", scale=scale),
        tooltip=["stage", "status", "duration_ms", "start", "end"]).properties(height=36 * len(t) + 40),
        width="stretch")
    st.caption(f"Source: `reports/hw10/spans.jsonl` filtered on trace_id = {trace_id}. "
               "queue_* = time a message waited in Kafka (producer timestamp -> consumer receive).")


PAGES = {"Summary": page_summary, "Evaluation": page_evaluation, "Trace lookup": page_trace}
st.sidebar.title(f"{cfg.PREFIX} operations")
st.sidebar.caption(f"{cfg.STUDENT_NAME} · DATA 260 HW10 · Municipal Transit Incidents")
choice = st.sidebar.radio("Page", list(PAGES))
PAGES[choice]()
