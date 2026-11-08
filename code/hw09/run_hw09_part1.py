"""HW9 Part 1 - Redis view counter for incidents, synced to s1346_rel every 10 views.

    python code/hw09/run_hw09_part1.py                    # incident id 42, 25 accesses, fresh counter
    python code/hw09/run_hw09_part1.py --incident-id 7 --accesses 25 --keep

Prints the expected "=== Testing Counter ===" output, then shows the Redis value and the MySQL
row (view_count = last multiple of 10), and times Redis INCR against a direct MySQL UPDATE per view.
"""
import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text  # noqa: E402

import hw09_config as cfg  # noqa: E402
from hw09_common import banner, get_engine, get_redis, setup_logging, write_json  # noqa: E402
from incident_cache import IncidentCache  # noqa: E402


def main() -> None:
    """Run the counter test."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--incident-id", type=int, default=42)
    ap.add_argument("--accesses", type=int, default=25)
    ap.add_argument("--keep", action="store_true", help="do not reset the counter first")
    ap.add_argument("--no-compare", action="store_true", help="skip the Redis vs MySQL timing")
    args = ap.parse_args()

    log = setup_logging("part1")
    banner(log, "Part 1 - view counter")
    r = get_redis()
    cache = IncidentCache(r, get_engine(), log)
    key = cfg.VIEWS_KEY.format(id=args.incident_id)

    before = cache.incident_row(args.incident_id)
    log.info("incident before: %s", before)
    if not args.keep:
        cache.reset_views(args.incident_id)
        log.info("reset: DEL %s and incidents.view_count = 0", key)

    print("\n=== Testing Counter ===\n", flush=True)
    incr_ms = []
    for n in range(1, args.accesses + 1):
        t0 = time.perf_counter()
        cache.increment_incident_views(args.incident_id,
                                       announce=lambda c, n=n: print(f"Access #{n}: Total = {c}", flush=True))
        incr_ms.append((time.perf_counter() - t0) * 1000)
    print(flush=True)

    redis_value = int(r.get(key))
    after = cache.incident_row(args.incident_id)
    log.info("Redis  GET %s -> %d", key, redis_value)
    log.info("MySQL  %s_rel.incidents id=%d view_count=%d (last sync at a multiple of %d; %d views not yet persisted)",
             cfg.PREFIX, args.incident_id, after["view_count"], cfg.SYNC_EVERY, redis_value - after["view_count"])
    log.info("updated_at unchanged by the view syncs: %s", before["updated_at"] == after["updated_at"])

    result = {"incident_id": args.incident_id, "key": key, "accesses": args.accesses,
              "redis_value": redis_value, "mysql_view_count": after["view_count"],
              "syncs": args.accesses // cfg.SYNC_EVERY, "incr_ms_mean": round(statistics.mean(incr_ms), 3)}

    if not args.no_compare:
        # Same number of views, but each one is a MySQL UPDATE (the slow design the scenario describes).
        engine = cache.engine
        db_ms = []
        for _ in range(args.accesses):
            t0 = time.perf_counter()
            with engine.begin() as conn:
                conn.execute(text("UPDATE incidents SET view_count = view_count + 1, updated_at = updated_at "
                                  "WHERE id = :id"), {"id": args.incident_id})
            db_ms.append((time.perf_counter() - t0) * 1000)
        with engine.begin() as conn:      # put the persisted value back to what the counter synced
            conn.execute(text("UPDATE incidents SET view_count = :c, updated_at = updated_at WHERE id = :id"),
                         {"c": after["view_count"], "id": args.incident_id})
        result.update(db_update_ms_mean=round(statistics.mean(db_ms), 3),
                      mysql_round_trips_redis_design=args.accesses // cfg.SYNC_EVERY,
                      mysql_round_trips_db_design=args.accesses)
        log.info("timing per view (%d views): Redis path mean %.3f ms (MySQL written %d times) | "
                 "MySQL UPDATE every view mean %.3f ms (MySQL written %d times)",
                 args.accesses, result["incr_ms_mean"], result["mysql_round_trips_redis_design"],
                 result["db_update_ms_mean"], args.accesses)
    log.info("saved %s", write_json("part1_counter.json", result))


if __name__ == "__main__":
    main()
