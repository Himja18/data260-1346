"""Rebuild reports/hw08/METRICS.md from the raw HW8 result files (make hw08-metrics).

Only reads reports/hw08/raw/*.json and verification.json; a missing file shows as "not run yet".
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hw08_config as cfg  # noqa: E402

RAW = cfg.RAW_DIR


def load(name: str):  # noqa: ANN201
    """JSON file from raw/ (or the report dir), None if missing."""
    for base in (RAW, cfg.REPORT_DIR):
        p = base / name
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def part1(lines: list[str]) -> None:
    """Part 1 table."""
    d = load("part1_demo.json")
    lines += ["## Part 1 - Request/response over Kafka", ""]
    if not d:
        lines += ["_not run yet (make hw08-demo)_", ""]
        return
    lat = {r.get("operation"): r.get("latency_ms") for r in d.get("sequence", []) if r.get("event") == "client_received"}
    c, g = d["create"], d["get"]
    lines += ["| Operation | correlation_id | success | result | correlation preserved | round trip (ms) |",
              "|---|---|---|---|---|---|",
              f"| CREATE_INCIDENT | `{c['correlation_id']}` | {c['response'].get('success')} | incident_id "
              f"`{c['response'].get('incident_id')}` | {c['response'].get('correlation_id') == c['correlation_id']} "
              f"| {lat.get('CREATE_INCIDENT')} |",
              f"| GET_INCIDENT | `{g['correlation_id']}` | {g['response'].get('success')} | fields round-trip: "
              f"{d.get('fields_round_trip')} | {g['response'].get('correlation_id') == g['correlation_id']} "
              f"| {lat.get('GET_INCIDENT')} |", ""]
    lines += ["| Error case | success | error | correlation preserved |", "|---|---|---|---|"]
    for name, e in d.get("errors", {}).items():
        lines.append(f"| {name} | {e['response'].get('success')} | {e['response'].get('error')} | "
                     f"{e['correlation_preserved']} |")
    lines.append("")


def part2(lines: list[str]) -> None:
    """Part 2 journeys."""
    j = load("part2_journeys.json")
    lines += ["## Part 2 - Three-agent pipeline", ""]
    if not j:
        lines += ["_not run yet (python code/kafka_agents/send_question.py)_", ""]
        return
    lines += ["| correlation_id | status | end-to-end (s) | stages in trace | reviewer notes |", "|---|---|---|---|---|"]
    for r in j:
        f = r["final"]
        stages = " -> ".join(t.get("stage", "?") for t in f.get("trace", []))
        lines.append(f"| `{r['correlation_id']}` | {f.get('status')} | {r['seconds']} | {stages} | "
                     f"{str(f.get('review_notes', '')).replace('|', '/')[:90]} |")
    lines.append("")


def part3(lines: list[str]) -> None:
    """Failure table + ordering details."""
    dup, death, poi, order = (load("part3_duplicate.json"), load("part3_consumer_death.json"),
                              load("part3_poison.json"), load("part3_ordering_summary.json"))
    lines += ["## Part 3 - Failure behaviour", "",
              "| Failure scenario | Before fix | After fix |", "|---|---|---|"]
    if dup:
        b, a = dup["before"], dup["after"]
        lines.append(f"| Duplicate delivery (same correlation_id sent twice) | no idempotency: processed "
                     f"{b['times_processed']}x, **{b['drafts_produced']} drafts** | correlation_id store: processed "
                     f"{a['times_processed']}x, skipped {a['duplicates_skipped']}, **{a['drafts_produced']} draft** |")
    else:
        lines.append("| Duplicate delivery | not run yet | not run yet |")
    if death:
        b, a = death["before"], death["after"]
        lines.append(f"| Consumer killed mid-work (SIGKILL during 8 s of work) | auto-commit: committed offset "
                     f"{b['committed_after_kill']} > message offset {b['message_offset']} at kill, redelivered="
                     f"{b['redelivered_after_restart']}, **{b['outcome']}** | commit after success: committed offset "
                     f"{a['committed_after_kill']} = message offset {a['message_offset']} at kill, redelivered="
                     f"{a['redelivered_after_restart']}, committed {a['committed_after_restart']} after restart, "
                     f"**{a['outcome']}** |")
    else:
        lines.append("| Consumer killed mid-work | not run yet | not run yet |")
    if poi:
        b, a = poi["before"], poi["after"]
        good = sum(1 for v in a["good_messages_processed"].values() if v)
        lines.append(f"| Poison message (invalid JSON, then JSON without `plan`) | no retry/DLQ: writer crashed "
                     f"{b['crashes']}x on the same offset, good message processed={b['good_message_processed']} "
                     f"(**partition blocked**) | {poi['max_attempts']} attempts each -> **{a['dead_letter_records']} "
                     f"records in {cfg.DEAD_LETTER_TOPIC}**, {good}/2 good messages processed |")
    else:
        lines.append("| Poison message | not run yet | not run yet |")
    if order:
        u, k = order["unkeyed"], order["keyed"]
        lines.append(f"| Two partitions / two consumers (20 msgs, 4 incidents) | no key: **{u['entities_in_order']}/"
                     f"{u['entities_total']} incidents in order**, {u['total_inversions']} inversions | key = "
                     f"incident id: **{k['entities_in_order']}/{k['entities_total']} in order**, "
                     f"{k['total_inversions']} inversions, each incident in one partition |")
        lines += ["", f"### Ordering detail (VERIFY_SEED {order['verify_seed']})", "",
                  "| Run | Incident | Partitions used | Processed seq | In order |", "|---|---|---|---|---|"]
        for run in ("unkeyed", "keyed"):
            for ent, info in order[run]["entities"].items():
                lines.append(f"| {run} | {ent} | {info['partitions']} | {info['processed_seq']} | "
                             f"{'yes' if info['in_order'] else 'NO'} |")
    else:
        lines.append("| Two partitions / two consumers | not run yet | not run yet |")
    lines.append("")


def verification(lines: list[str]) -> None:
    """verification.json summary."""
    v = load("verification.json")
    lines += ["## verification.json", ""]
    if not v:
        lines += ["_not run yet (make verify-hw08)_", ""]
        return
    lines += [f"{v['passed']}/{v['total']} checks passed ({v['mode']}) on commit `{v['commit'][:12]}`", "",
              "| Check | Result |", "|---|---|"]
    lines += [f"| {c['name']} | {'PASS' if c['passed'] else 'FAIL'} |" for c in v["checks"]]
    lines.append("")


def main() -> None:
    """Write METRICS.md."""
    lines = [f"# HW8 METRICS - {cfg.STUDENT_NAME} ({cfg.PREFIX})", "",
             "| SID4 | PORT_BASE | PREFIX | SEED | VERIFY_SEED | DOMAIN_ID | Model | Hardware |",
             "|---|---|---|---|---|---|---|---|",
             f"| {cfg.SID4} | {cfg.PORT_BASE} | {cfg.PREFIX} | {cfg.SEED} | {cfg.VERIFY_SEED} | {cfg.DOMAIN_ID} "
             f"(Municipal Transit Incidents) | {cfg.MODEL_DESCRIPTION} | {cfg.HARDWARE} |", ""]
    part1(lines)
    part2(lines)
    part3(lines)
    verification(lines)
    cfg.ensure_dirs()
    (cfg.REPORT_DIR / "METRICS.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote reports/hw08/METRICS.md")


if __name__ == "__main__":
    main()
