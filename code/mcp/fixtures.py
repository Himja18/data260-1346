"""Shared offline fixtures for the HW5 tests (no DB / network / LLM)."""
from resilience import TransientError

# ---- fixtures ---------------------------------------------------------------
INCIDENTS = [
    {"id": 1, "incident_code": "INC-000001", "route_title": "Route 5 - 15 min delay at Main St",
     "category": "Delay", "passengers_affected": 35, "line_code": "L-005"},
    {"id": 2, "incident_code": "INC-000002", "route_title": "Route 5 - Breakdown at Oak St",
     "category": "Breakdown", "passengers_affected": 20, "line_code": "L-005"},
    {"id": 3, "incident_code": "INC-000003", "route_title": "Route 6 - Detour on Pine St",
     "category": "Service Change", "passengers_affected": 0, "line_code": "L-006"},
]
LINES = {"L-005": ("Route 5 - Harbor", "Bus"), "L-006": ("Route 6 - Uptown", "Bus")}


class FakeRepo:
    """Same interface as SqlRepository, backed by the lists above."""
    def __init__(self):
        self.calls = 0

    def search_incidents(self, category, line_code, text_query, limit):
        self.calls += 1
        rows = [r for r in INCIDENTS
                if (category is None or r["category"] == category)
                and (line_code is None or r["line_code"] == line_code)
                and (text_query is None or text_query.lower() in r["route_title"].lower())]
        return sorted(rows, key=lambda r: -r["id"])[:limit]

    def get_incident(self, code):
        self.calls += 1
        for r in INCIDENTS:
            if r["incident_code"] == code:
                name, mode = LINES[r["line_code"]]
                return dict(r, line_name=name, line_mode=mode)
        return None

    def line_exists(self, code):
        self.calls += 1
        return code in LINES

    def category_stats(self, line_code):
        self.calls += 1
        out = {}
        for r in INCIDENTS:
            if line_code is None or r["line_code"] == line_code:
                c = out.setdefault(r["category"], {"category": r["category"], "incidents": 0,
                                                   "passengers_affected": 0})
                c["incidents"] += 1
                c["passengers_affected"] += r["passengers_affected"]
        return sorted(out.values(), key=lambda c: -c["incidents"])


class AlwaysDown:
    """Every storage call fails with a transient error."""
    def __getattr__(self, name):
        def boom(*a, **k):
            raise TransientError("database unreachable (simulated)")
        return boom


