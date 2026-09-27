"""HW4 Part 3.8: add ONE index and show EXPLAIN before/after.

Index:  ix_incidents_category ON incidents(category)   (see migrations/002_part3_category_index.sql)

Explained queries (what the app runs when it filters by category):
  Q1  the /api/incidents/fixed?category=Accident&limit=50 query shape
  Q2  count of incidents in one category
Steps: drop the index if present -> EXPLAIN + EXPLAIN ANALYZE (before) -> CREATE INDEX
       -> ANALYZE TABLE -> EXPLAIN + EXPLAIN ANALYZE (after). Also times each query 50x.
Output: printed and saved to (repo root)/reports/hw04/raw/explain_before_after.txt

    python explain_index.py
"""
import statistics
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from database import DB_NAME, engine

INDEX = "ix_incidents_category"
QUERIES = {
    "Q1 page of one category (fixed endpoint shape)": (
        "SELECT i.id, i.route_title, i.category, i.created_at, l.code, l.name, l.mode "
        "FROM incidents i LEFT OUTER JOIN transit_lines l ON l.id = i.line_id "
        "WHERE i.category = 'Accident' ORDER BY i.id DESC LIMIT 50"),
    "Q2 count in one category": (
        "SELECT COUNT(*) FROM incidents WHERE category = 'Accident'"),
}
REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "reports" / "hw04" / "raw" / "explain_before_after.txt"
lines_out: list[str] = []


def out(s=""):
    print(s)
    lines_out.append(s)


def table(rows, keys):
    cols = [str(k) for k in keys]
    data = [["NULL" if v is None else str(v) for v in r] for r in rows]
    widths = [max(len(c), *(len(d[i]) for d in data)) for i, c in enumerate(cols)]
    fmt = " | ".join("{:<%d}" % w for w in widths)
    out(fmt.format(*cols))
    out("-+-".join("-" * w for w in widths))
    for d in data:
        out(fmt.format(*d))


def index_exists(conn) -> bool:
    return bool(conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema = :db AND table_name = 'incidents' AND index_name = :ix"),
        {"db": DB_NAME, "ix": INDEX}).scalar())


def explain_all(conn, label):
    out(f"\n==================== {label} ====================")
    for name, sql in QUERIES.items():
        out(f"\n--- {name}\n{sql}\n")
        res = conn.execute(text("EXPLAIN " + sql))
        table(res.fetchall(), res.keys())
        out("\nEXPLAIN ANALYZE:")
        for (plan,) in conn.execute(text("EXPLAIN ANALYZE " + sql)):
            out(plan)
        times = []
        for _ in range(50):
            t0 = time.perf_counter()
            conn.execute(text(sql)).fetchall()
            times.append((time.perf_counter() - t0) * 1000)
        out(f"\nmedian of 50 runs: {statistics.median(times):.3f} ms")


def main():
    out(f"HW4 Part 3.8 EXPLAIN before/after - {datetime.now().isoformat(timespec='seconds')}")
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM incidents")).scalar()
        out(f"incidents rows: {n}")
        if index_exists(conn):
            conn.execute(text(f"DROP INDEX {INDEX} ON incidents"))
            out(f"(dropped existing {INDEX} to capture the 'before' state)")
        conn.execute(text("ANALYZE TABLE incidents")).fetchall()
        explain_all(conn, "BEFORE index")

        conn.execute(text(f"CREATE INDEX {INDEX} ON incidents (category)"))
        conn.execute(text("ANALYZE TABLE incidents")).fetchall()
        out(f"\nCREATE INDEX {INDEX} ON incidents (category);")
        explain_all(conn, "AFTER index")

        res = conn.execute(text("SHOW INDEX FROM incidents"))
        out("\n==================== SHOW INDEX FROM incidents ====================")
        table([(r.Key_name, r.Seq_in_index, r.Column_name, r.Non_unique) for r in res],
              ["Key_name", "Seq_in_index", "Column_name", "Non_unique"])
        conn.commit()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines_out) + "\n")
    print(f"\nSaved to {OUT}")


if __name__ == "__main__":
    main()
