"""Data access for the s1346_rel domain tools.

SqlRepository talks to MySQL (or any SQLAlchemy URL, e.g. SQLite in tests).
The tool layer only depends on these three methods, so tests can inject a
fake repository instead (dependency injection, Part 4)."""
import os
from typing import Optional
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text


def default_url() -> str:
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    user = os.getenv("MYSQL_USER", "root")
    pw = quote_plus(os.getenv("MYSQL_PASSWORD", ""))
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    return f"mysql+pymysql://{user}:{pw}@{host}:{port}/s1346_rel"


def _row(r) -> dict:
    d = dict(r._mapping)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


class SqlRepository:
    def __init__(self, url: Optional[str] = None):
        url = url or default_url()
        connect_args = {}
        if url.startswith("mysql"):
            # Storage-level timeouts (seconds) so a hung DB can't block a tool forever.
            connect_args = {"connect_timeout": 5, "read_timeout": 10, "write_timeout": 10}
        self.engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)

    def search_incidents(self, category, line_code, text_query, limit) -> list[dict]:
        sql = """
            SELECT i.id, i.incident_code, i.route_title, i.category,
                   i.passengers_affected, l.code AS line_code, i.created_at
            FROM incidents i LEFT JOIN transit_lines l ON l.id = i.line_id
            WHERE 1 = 1"""
        params = {"limit": limit}
        if category:
            sql += " AND i.category = :category"
            params["category"] = category
        if line_code:
            sql += " AND l.code = :line_code"
            params["line_code"] = line_code
        if text_query:
            sql += " AND i.route_title LIKE :q"
            params["q"] = f"%{text_query}%"
        sql += " ORDER BY i.id DESC LIMIT :limit"
        with self.engine.connect() as c:
            return [_row(r) for r in c.execute(text(sql), params)]

    def get_incident(self, incident_code) -> Optional[dict]:
        sql = """
            SELECT i.id, i.incident_code, i.route_title, i.category,
                   i.passengers_affected, i.created_at, i.updated_at,
                   l.code AS line_code, l.name AS line_name, l.mode AS line_mode
            FROM incidents i LEFT JOIN transit_lines l ON l.id = i.line_id
            WHERE i.incident_code = :code"""
        with self.engine.connect() as c:
            r = c.execute(text(sql), {"code": incident_code}).first()
            return _row(r) if r else None

    def line_exists(self, line_code) -> bool:
        with self.engine.connect() as c:
            return c.execute(text("SELECT 1 FROM transit_lines WHERE code = :c"),
                             {"c": line_code}).first() is not None

    def category_stats(self, line_code) -> list[dict]:
        sql = """
            SELECT i.category, COUNT(*) AS incidents,
                   COALESCE(SUM(i.passengers_affected), 0) AS passengers_affected
            FROM incidents i LEFT JOIN transit_lines l ON l.id = i.line_id"""
        params = {}
        if line_code:
            sql += " WHERE l.code = :line_code"
            params["line_code"] = line_code
        sql += " GROUP BY i.category ORDER BY incidents DESC"
        with self.engine.connect() as c:
            return [{k: (int(v) if k != "category" else v) for k, v in _row(r).items()}
                    for r in c.execute(text(sql), params)]
