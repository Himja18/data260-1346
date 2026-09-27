"""HW4 Part 3 seed: 200 transit_lines + 5,000 incidents, deterministic (SEED = 1346).

Every seeded incident is linked to one transit line (incidents.line_id -> transit_lines.id),
so each line has ~25 incidents. Same SEED -> same rows -> same checksum.

Run from code/backend with the MySQL env vars set:
    python seed_part3.py            # seed (refuses if lines already exist)
    python seed_part3.py --reset    # delete previously seeded rows, then seed again
Tables come from schema.sql (the migration); this script only inserts rows.
"""
import argparse
import hashlib
import random
import sys
from datetime import datetime, timedelta

from sqlalchemy import delete, func, insert, select

from database import db_session_basede26
from models import Incident, TransitLine

SEED = 1346
N_LINES = 200
N_INCIDENTS = 5000

# 200 lines split by mode: (mode, count, name prefix)
MODES = [("Bus", 120, "Route"), ("Light Rail", 40, "LRT Line"),
         ("Subway", 25, "Subway Line"), ("Commuter Rail", 15, "Commuter Line")]
CORRIDORS = ["Downtown Loop", "Crosstown", "Airport Express", "Harbor", "University",
             "Northside", "Eastside", "Southgate", "Westfield", "Riverside",
             "Market Street", "Civic Center", "Hillcrest", "Lakeshore", "Medical Center"]
STREETS = ["Main St", "5th Ave", "Market St", "Oak St", "Broadway", "1st St",
           "Park Ave", "Elm St", "Central Station", "Union Square", "Mission Blvd",
           "Pine St", "King St", "Harbor Dr", "College Ave", "Airport Blvd"]
CATEGORIES = ["Delay", "Breakdown", "Service Change", "Accident"]
CATEGORY_WEIGHTS = [45, 25, 20, 10]
TEMPLATES = {
    "Delay": "{line} - {mins} min delay at {street}",
    "Breakdown": "{line} - Vehicle breakdown near {street}",
    "Service Change": "{line} - Detour around {street}",
    "Accident": "{line} - Minor collision at {street}",
}
END_TIME = datetime(2026, 9, 1)            # fixed, so reruns produce identical timestamps


def build_lines(rng: random.Random) -> list[dict]:
    rows, n = [], 0
    for mode, count, prefix in MODES:
        for _ in range(count):
            n += 1
            rows.append({"code": f"L-{n:03d}",
                         "name": f"{prefix} {n} - {rng.choice(CORRIDORS)}",
                         "mode": mode})
    assert len(rows) == N_LINES
    return rows


def build_incidents(rng: random.Random, lines: list) -> list[dict]:
    # Ascending timestamps so newer ids are also newer reports.
    offsets = sorted((rng.randint(0, 365 * 86400) for _ in range(N_INCIDENTS)), reverse=True)
    rows = []
    for off in offsets:
        line = rng.choice(lines)                          # (id, name)
        category = rng.choices(CATEGORIES, weights=CATEGORY_WEIGHTS)[0]
        title = TEMPLATES[category].format(line=line.name.split(" - ")[0],
                                           mins=rng.randint(5, 45),
                                           street=rng.choice(STREETS))
        rows.append({"route_title": title, "category": category, "line_id": line.id,
                     "created_at": END_TIME - timedelta(seconds=off)})
    return rows


def checksum(lines: list[dict], incidents: list[dict], line_code_by_id: dict) -> str:
    h = hashlib.sha256()
    for l in lines:
        h.update(f"{l['code']}|{l['name']}|{l['mode']}\n".encode())
    for i in incidents:
        h.update(f"{i['route_title']}|{i['category']}|{line_code_by_id[i['line_id']]}|"
                 f"{i['created_at'].isoformat()}\n".encode())
    return h.hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="remove seeded rows first")
    args = ap.parse_args()

    rng = random.Random(SEED)
    db = db_session_basede26()
    try:
        existing = db.scalar(select(func.count()).select_from(TransitLine))
        if existing and not args.reset:
            print(f"transit_lines already has {existing} rows. Use --reset to reseed.")
            sys.exit(1)
        if args.reset:
            removed = db.execute(delete(Incident).where(Incident.line_id.is_not(None))).rowcount
            db.execute(delete(TransitLine))
            db.commit()
            print(f"Reset: removed {removed} seeded incidents and all transit_lines")

        lines = build_lines(rng)
        db.execute(insert(TransitLine), lines)
        db.flush()
        line_rows = db.execute(select(TransitLine.id, TransitLine.name, TransitLine.code)
                               .order_by(TransitLine.id)).all()

        incidents = build_incidents(rng, line_rows)
        db.execute(insert(Incident), incidents)
        db.commit()

        code_by_id = {r.id: r.code for r in line_rows}
        n_lines = db.scalar(select(func.count()).select_from(TransitLine))
        n_inc = db.scalar(select(func.count()).select_from(Incident))
        n_linked = db.scalar(select(func.count()).select_from(Incident)
                             .where(Incident.line_id.is_not(None)))
        per_cat = db.execute(select(Incident.category, func.count())
                             .where(Incident.line_id.is_not(None))
                             .group_by(Incident.category).order_by(Incident.category)).all()

        print(f"SEED={SEED}")
        print(f"transit_lines: {n_lines}")
        print(f"incidents total: {n_inc}  (seeded, linked to a line: {n_linked})")
        print("seeded incidents per category: " + ", ".join(f"{c}={n}" for c, n in per_cat))
        print("sample:")
        for r in incidents[-3:]:
            print(f"  {code_by_id[r['line_id']]}  {r['category']:<14} {r['route_title']}")
        print(f"checksum (same SEED -> same value): {checksum(lines, incidents, code_by_id)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
