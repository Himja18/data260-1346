"""HW9 Part 3.5 - stale answer, then invalidation with the stored data-version marker.

    python code/hw09/run_hw09_part3_stale.py                       # INC-000105, +40 passengers
    python code/hw09/run_hw09_part3_stale.py --code INC-000105 --add-passengers 40 --keep-change

Steps
 1. Show the s1346_rel row; make sure the question is cached (miss -> HW8 pipeline -> stored with version v1).
 2. UPDATE incidents SET passengers_affected = old + N   (the cached answer is now wrong).
 3. Ask again with the version check OFF  -> HIT, the OLD answer is returned  (stale hit).
 4. Ask again with the version check ON   -> stored v1 != current v2 -> entry deleted -> pipeline -> new answer.
 5. Ask once more                          -> HIT on the fresh entry (version matches).
 6. Restore the original row (unless --keep-change).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hw09_config as cfg  # noqa: E402
from hw09_common import banner, setup_logging, short, write_json  # noqa: E402
from run_hw09_part2 import build_cache  # noqa: E402


def main() -> None:
    """Run the stale-answer demonstration."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default="INC-000105")
    ap.add_argument("--question", default=None)
    ap.add_argument("--add-passengers", type=int, default=40)
    ap.add_argument("--keep-change", action="store_true")
    ap.add_argument("--fake-agent", action="store_true", help="offline test only")
    args = ap.parse_args()
    question = args.question or f"How many passengers were affected by incident {args.code}?"
    log = setup_logging("part3-stale")
    banner(log, "Part 3.5 - stale answers and invalidation")
    cache = build_cache(log, cfg.DEFAULT_THRESHOLD, args.fake_agent)
    facts = cache.facts
    steps = {}

    original = facts.facts_for_codes([args.code]).get(args.code)
    if original is None:
        raise SystemExit(f"{args.code} is not in {cfg.PREFIX}_rel.incidents")
    log.info("[1] s1346_rel row: %s | passengers_affected=%s | version=%s", args.code,
             original["passengers_affected"], facts.data_version([args.code]))
    first = cache.ask(question, version_check=True)
    log.info("[1] cached: is_cached=%s data_version=%s answer=\"%s\"", first.is_cached, first.data_version,
             short(first.answer, 200))
    steps["1_cached_answer"] = first.to_dict()

    new_value = int(original["passengers_affected"]) + args.add_passengers
    row = facts.update_incident(args.code, passengers_affected=new_value)
    log.info("[2] UPDATE incidents SET passengers_affected = %d WHERE incident_code = '%s'  (was %s) -> version now %s",
             new_value, args.code, original["passengers_affected"], facts.data_version([args.code]))
    steps["2_update"] = {"code": args.code, "old": original["passengers_affected"], "new": row["passengers_affected"]}

    stale = cache.ask(question, version_check=False)
    log.info("[3] version check OFF: is_cached=%s sim=%s latency=%.1f ms", stale.is_cached, stale.similarity,
             stale.latency_ms)
    log.info("[3] returned answer (built from passengers_affected=%s): \"%s\"", original["passengers_affected"],
             short(stale.answer, 200))
    log.info("[3] database now says passengers_affected=%d  ->  STALE HIT: %s", new_value,
             stale.is_cached and stale.answer == first.answer)
    steps["3_stale_hit"] = stale.to_dict()

    fresh = cache.ask(question, version_check=True)
    log.info("[4] version check ON : is_cached=%s reason=%s latency=%.1f ms new version=%s", fresh.is_cached,
             fresh.reason, fresh.latency_ms, fresh.data_version)
    log.info("[4] new answer: \"%s\"", short(fresh.answer, 200))
    log.info("[4] new answer mentions %d: %s", new_value, str(new_value) in fresh.answer)
    steps["4_invalidated_and_recomputed"] = fresh.to_dict()

    again = cache.ask(question, version_check=True)
    log.info("[5] ask again: is_cached=%s reason=%s latency=%.1f ms (version check %.2f ms)", again.is_cached,
             again.reason, again.latency_ms, again.timings_ms.get("version_check", 0.0))
    steps["5_hit_on_fresh_entry"] = again.to_dict()

    if not args.keep_change:
        facts.update_incident(args.code, passengers_affected=original["passengers_affected"])
        log.info("[6] restored %s passengers_affected=%s (the entry stored in [4] is now stale again and would "
                 "be invalidated the same way on its next hit)", args.code, original["passengers_affected"])
    log.info("saved %s", write_json("part3_stale.json", {"question": question, "steps": steps}))
    cache.agent.close()


if __name__ == "__main__":
    main()
