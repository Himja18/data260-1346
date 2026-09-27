"""Per-request SQL statement counter (HW4 Part 3).

Hooks SQLAlchemy's before_cursor_execute event on the shared engine. Code that
wants to count its queries wraps them in `with count_sql() as stmts:`; every SQL
statement sent to MySQL inside that block is appended to `stmts`.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event

from database import engine

_current: ContextVar[list | None] = ContextVar("sql_statements", default=None)


@event.listens_for(engine, "before_cursor_execute")
def _record(conn, cursor, statement, parameters, context, executemany):
    box = _current.get()
    if box is not None:
        box.append(statement)


@contextmanager
def count_sql():
    box: list[str] = []
    token = _current.set(box)
    try:
        yield box
    finally:
        _current.reset(token)
