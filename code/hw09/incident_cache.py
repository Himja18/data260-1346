"""HW9 - IncidentCache: Redis in front of s1346_rel.incidents.

Part 1:   increment_incident_views(incident_id)  - Redis INCR on every view, MySQL sync every 10.
Part 3.5: facts_for_codes() / data_version()     - the s1346_rel facts a cached answer was built from,
          and a fingerprint of them (the data-version marker stored with each cache entry).
"""
import hashlib
import logging
from typing import Any, Optional

from sqlalchemy import bindparam, text

import hw09_config as cfg

FACT_FIELDS = ("route_title", "category", "passengers_affected", "line_code", "line_name", "created_at")


class IncidentNotFound(LookupError):
    """No incidents row with that id / code."""


class IncidentCache:
    """Database + cache access for the primary entity (Incident)."""

    def __init__(self, redis_client: Any, engine: Any, log: logging.Logger,
                 sync_every: int = cfg.SYNC_EVERY) -> None:
        self.redis_client = redis_client
        self.engine = engine
        self.log = log
        self.sync_every = sync_every

    # ------------------------------------------------------------------ Part 1 ----
    def increment_incident_views(self, incident_id: int, announce: Any = None) -> int:
        """Count one view of an incident in Redis; persist the count to MySQL every `sync_every` views.

        Returns the current total. On a cold cache (key missing, e.g. after a Redis restart) the
        counter continues from the last value persisted in incidents.view_count.
        `announce(count)` (optional) is called right after the INCR, so a demo can print the total
        before the sync message.
        """
        key = cfg.VIEWS_KEY.format(id=incident_id)
        if not self.redis_client.exists(key):
            self.redis_client.set(key, self.db_view_count(incident_id), nx=True)
        count = int(self.redis_client.incr(key))           # atomic INCR - safe with concurrent viewers
        if announce:
            announce(count)
        if count % self.sync_every == 0:
            self._persist_views(incident_id, count)
            self.log.info("✓ Synced views to database (incidents.id=%s view_count=%d, key=%s)",
                          incident_id, count, key)
        return count

    def db_view_count(self, incident_id: int) -> int:
        """incidents.view_count (raises IncidentNotFound)."""
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT view_count FROM incidents WHERE id = :id"),
                               {"id": incident_id}).first()
        if row is None:
            raise IncidentNotFound(f"incident id {incident_id} not found in {cfg.PREFIX}_rel.incidents")
        return int(row[0] or 0)

    def _persist_views(self, incident_id: int, count: int) -> None:
        """Write the count to MySQL. updated_at = updated_at stops MySQL's ON UPDATE CURRENT_TIMESTAMP:
        a view is not a change to the incident itself."""
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE incidents SET view_count = :c, updated_at = updated_at WHERE id = :id"),
                         {"c": count, "id": incident_id})

    def reset_views(self, incident_id: int) -> None:
        """Demo helper: delete the Redis counter and zero the persisted count."""
        self.redis_client.delete(cfg.VIEWS_KEY.format(id=incident_id))
        self._persist_views(incident_id, 0)

    def incident_row(self, incident_id: int) -> dict:
        """incidents row (subset) for display."""
        with self.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT id, incident_code, route_title, category, passengers_affected, view_count, updated_at "
                "FROM incidents WHERE id = :id"), {"id": incident_id}).mappings().first()
        if row is None:
            raise IncidentNotFound(f"incident id {incident_id} not found")
        return dict(row)

    # ---------------------------------------------------------------- Part 3.5 ----
    def facts_for_codes(self, codes: list[str]) -> dict[str, dict]:
        """incident_code -> facts from incidents JOIN transit_lines (missing codes are left out)."""
        if not codes:
            return {}
        stmt = text(
            "SELECT i.id, i.incident_code, i.route_title, i.category, i.passengers_affected, i.created_at, "
            "       l.code AS line_code, l.name AS line_name "
            "FROM incidents i LEFT JOIN transit_lines l ON l.id = i.line_id "
            "WHERE i.incident_code IN :codes").bindparams(bindparam("codes", expanding=True))
        with self.engine.connect() as conn:
            rows = conn.execute(stmt, {"codes": list(codes)}).mappings().all()
        return {r["incident_code"]: dict(r) for r in rows}

    @staticmethod
    def fingerprint(facts: dict[str, dict], codes: list[str]) -> str:
        """Data-version marker: hash of exactly the fields an answer was built from."""
        if not codes:
            return cfg.STATIC_VERSION
        h = hashlib.sha1()
        for code in sorted(codes):
            row = facts.get(code)
            h.update(code.encode())
            h.update(b"|missing" if row is None else
                     ("|" + "|".join(str(row.get(f)) for f in FACT_FIELDS)).encode())
        return "v:" + h.hexdigest()[:12]

    def data_version(self, codes: list[str]) -> str:
        """Current data-version marker for these incident codes (one primary-key-sized query)."""
        return self.fingerprint(self.facts_for_codes(codes), codes)

    @staticmethod
    def facts_text(facts: dict[str, dict], codes: list[str]) -> str:
        """Facts block appended to the question sent to the agent pipeline."""
        lines = []
        for code in codes:
            r = facts.get(code)
            if r is None:
                lines.append(f"- {code}: no such incident in {cfg.PREFIX}_rel")
                continue
            lines.append(f"- {code}: route_title=\"{r['route_title']}\"; category={r['category']}; "
                         f"passengers_affected={r['passengers_affected']}; "
                         f"line={r.get('line_code') or '-'} ({r.get('line_name') or '-'}); "
                         f"reported_at={r['created_at']}")
        return "\n".join(lines)

    def update_incident(self, code: str, **fields: Any) -> Optional[dict]:
        """Part 3.5: change an incident row (category / passengers_affected) - this is what makes answers stale."""
        allowed = {k: v for k, v in fields.items() if k in ("category", "passengers_affected", "route_title")}
        if not allowed:
            return None
        sets = ", ".join(f"{k} = :{k}" for k in allowed)
        with self.engine.begin() as conn:
            conn.execute(text(f"UPDATE incidents SET {sets} WHERE incident_code = :code"),  # noqa: S608 - keys whitelisted
                         {**allowed, "code": code})
        return self.facts_for_codes([code]).get(code)
