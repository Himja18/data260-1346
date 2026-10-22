"""HW7 Part 4 - read prices out of the pricing snapshot and build the tool-computed cost breakdown.

extract_prices(text)   regexes over the snapshot text -> Prices (+ the exact snippet each
                       value came from, for citations). Nothing is hard-coded: a value that
                       is not found stays None and is reported as a caveat.
cost_breakdown(...)    runs csv_sql + calculator (the same tools the agent has, logged in the
                       timeline as phase "report") to produce the totals, break-even point,
                       weekly table and per-rider split shown in the results panel.

Billing assumptions (stated as caveats in every report): minutes are billed per started
minute (CEIL), every rider in the file would hold a membership for the whole period covered,
rides with zero/negative duration are excluded.
"""
import math
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

MONEY = r"\$\s?(\d+(?:\.\d{1,2})?)"


@dataclass
class Prices:
    """Prices found in the snapshot (None = not found)."""
    monthly: float | None = None
    unlock: float | None = None
    ppu_classic_per_min: float | None = None
    ppu_ebike_per_min: float | None = None
    member_free_min: float | None = None
    member_classic_over_per_min: float | None = None
    member_ebike_per_min: float | None = None
    snippets: dict = field(default_factory=dict)

    @property
    def missing(self) -> list[str]:
        """Fields the snapshot did not provide."""
        return [k for k, v in asdict(self).items() if k != "snippets" and v is None]


def _ctx(text: str, m: re.Match, pad: int = 40) -> str:
    return " ".join(text[max(0, m.start() - pad): m.end() + pad].split())


def extract_prices(text: str) -> Prices:
    """Pull the membership / pay-per-use numbers out of the pricing page text."""
    t = " ".join(text.split())
    p = Prices()
    if m := re.search(MONEY + r"\s*/\s*(?:mo\b|month)", t, re.I):
        p.monthly, p.snippets["monthly"] = float(m.group(1)), _ctx(t, m)
    if m := re.search(MONEY + r"\s*(?:to\s+)?unlock,?\s*(?:then|\+)\s*" + MONEY + r"\s*/\s*min", t, re.I):
        p.unlock, p.ppu_classic_per_min = float(m.group(1)), float(m.group(2))
        p.snippets["single_classic"] = _ctx(t, m)
    ebike = [m for m in re.finditer(MONEY + r"\s*unlock\s*\+\s*" + MONEY + r"\s*/\s*min", t, re.I)]
    if ebike:                                   # pay-per-use e-bike: the highest per-minute rate quoted
        m = max(ebike, key=lambda x: float(x.group(2)))
        if p.unlock is None:
            p.unlock = float(m.group(1))
        p.ppu_ebike_per_min, p.snippets["single_ebike"] = float(m.group(2)), _ctx(t, m)
    free = [m for m in re.finditer(r"(\d+)\s*min(?:utes)?\s*free,?\s*then\s*" + MONEY + r"\s*/\s*min", t, re.I)]
    if free:                                    # membership: the longest free window (45 > day pass 30)
        m = max(free, key=lambda x: int(x.group(1)))
        p.member_free_min, p.member_classic_over_per_min = float(m.group(1)), float(m.group(2))
        p.snippets["member_classic"] = _ctx(t, m)
    fu = [m for m in re.finditer(r"free unlocks?\s*\+\s*" + MONEY + r"\s*/\s*min", t, re.I)]
    if fu:                                      # member e-bike: the lowest "free unlock" rate
        m = min(fu, key=lambda x: float(x.group(1)))
        p.member_ebike_per_min, p.snippets["member_ebike"] = float(m.group(1)), _ctx(t, m)
    return p


def summary_sql(p: Prices) -> str:
    """One SELECT that prices every trip under both plans."""
    return f"""SELECT COUNT(*) AS rides, COUNT(DISTINCT rider_key) AS riders,
  ROUND(AVG(duration_min), 2) AS avg_duration_min,
  SUM(CASE WHEN bike_type = 'electric_bike' THEN 1 ELSE 0 END) AS ebike_rides,
  SUM(CASE WHEN duration_min > {p.member_free_min} THEN 1 ELSE 0 END) AS rides_over_free_minutes,
  ROUND(SUM(CASE WHEN bike_type = 'electric_bike' THEN {p.unlock} + {p.ppu_ebike_per_min} * CEIL(duration_min)
                 ELSE {p.unlock} + {p.ppu_classic_per_min} * CEIL(duration_min) END), 2) AS payg_total,
  ROUND(SUM(CASE WHEN bike_type = 'electric_bike' THEN {p.member_ebike_per_min} * CEIL(duration_min)
                 ELSE {p.member_classic_over_per_min} * GREATEST(CEIL(duration_min) - {p.member_free_min}, 0) END), 2)
    AS member_residual_total,
  CAST(MIN(CAST(started_at AS TIMESTAMP)) AS VARCHAR) AS first_ride,
  CAST(MAX(CAST(started_at AS TIMESTAMP)) AS VARCHAR) AS last_ride,
  DATE_DIFF('day', MIN(CAST(started_at AS TIMESTAMP)), MAX(CAST(started_at AS TIMESTAMP))) + 1 AS days_covered
FROM trips WHERE duration_min > 0"""


def weekly_sql(p: Prices) -> str:
    """Per-week ride count, average duration and spend under both plans."""
    return f"""SELECT CAST(week_start AS VARCHAR) AS week, COUNT(*) AS rides,
  ROUND(AVG(duration_min), 1) AS avg_duration_min,
  ROUND(SUM(CASE WHEN bike_type = 'electric_bike' THEN {p.unlock} + {p.ppu_ebike_per_min} * CEIL(duration_min)
                 ELSE {p.unlock} + {p.ppu_classic_per_min} * CEIL(duration_min) END), 2) AS payg_spend,
  ROUND(SUM(CASE WHEN bike_type = 'electric_bike' THEN {p.member_ebike_per_min} * CEIL(duration_min)
                 ELSE {p.member_classic_over_per_min} * GREATEST(CEIL(duration_min) - {p.member_free_min}, 0) END), 2)
    AS member_residual_spend
FROM trips WHERE duration_min > 0 GROUP BY week_start ORDER BY week_start"""


def per_rider_sql(p: Prices, months: int) -> str:
    """How many riders individually come out ahead with a membership."""
    return f"""SELECT SUM(CASE WHEN member_cost < payg_cost THEN 1 ELSE 0 END) AS riders_cheaper_with_membership,
  COUNT(*) AS riders, ROUND(MEDIAN(rides), 1) AS median_rides_per_rider
FROM (SELECT rider_key, COUNT(*) AS rides,
        SUM(CASE WHEN bike_type = 'electric_bike' THEN {p.unlock} + {p.ppu_ebike_per_min} * CEIL(duration_min)
                 ELSE {p.unlock} + {p.ppu_classic_per_min} * CEIL(duration_min) END) AS payg_cost,
        {months} * {p.monthly} + SUM(CASE WHEN bike_type = 'electric_bike' THEN {p.member_ebike_per_min} * CEIL(duration_min)
                 ELSE {p.member_classic_over_per_min} * GREATEST(CEIL(duration_min) - {p.member_free_min}, 0) END) AS member_cost
      FROM trips WHERE duration_min > 0 GROUP BY rider_key) t"""


DataCaveatsSQL = """SELECT SUM(CASE WHEN duration_min <= 0 THEN 1 ELSE 0 END) AS non_positive_durations,
  SUM(CASE WHEN duration_min > 1440 THEN 1 ELSE 0 END) AS over_24h,
  SUM(CASE WHEN bike_type NOT IN ('classic_bike', 'electric_bike') THEN 1 ELSE 0 END) AS other_bike_types
FROM trips"""


def cost_breakdown(prices: Prices, run_sql: Callable[[str], dict], calc: Callable[[str, str], dict],
                   missing_columns: list[str]) -> dict:
    """Tool-computed comparison. run_sql/calc are the logged tool wrappers."""
    caveats = [
        "Minutes billed per started minute (CEIL of trip duration); taxes and fees not included.",
        "Each rider in the file is assumed to hold a membership for every 30-day period the file covers.",
        "Trips with zero or negative duration are excluded.",
    ]
    if prices.missing:
        return {"ok": False, "error": f"pricing snapshot did not provide: {', '.join(prices.missing)}",
                "caveats": caveats}
    if "rider_id" in missing_columns:
        caveats.append("The CSV has no rider_id column, so every trip is treated as one rider.")
    other_missing = [c for c in missing_columns if c != "rider_id"]
    if other_missing:
        caveats.append(f"Missing columns: {', '.join(other_missing)} (defaults used: classic bike).")
    s = run_sql(summary_sql(prices))
    if not s.get("success"):
        return {"ok": False, "error": s.get("error"), "caveats": caveats}
    row = s["data"]["rows"][0]
    months = max(1, math.ceil(row["days_covered"] / 30))
    riders = row["riders"]
    member_total = calc(f"{riders} * {months} * {prices.monthly} + {row['member_residual_total']}", "USD")
    payg_total = float(row["payg_total"])
    mt = member_total["data"]["value"]
    per_ride_payg = calc(f"{payg_total} / {row['rides']}", "USD/ride")["data"]["value"]
    per_ride_member_residual = calc(f"{row['member_residual_total']} / {row['rides']}", "USD/ride")["data"]["value"]
    saving = per_ride_payg - per_ride_member_residual
    if saving > 0:
        be = calc(f"{prices.monthly} / ({per_ride_payg} - {per_ride_member_residual})", "rides/rider-month")
        break_even = be["data"]["value"]
    else:
        break_even = None
    actual = calc(f"{row['rides']} / ({riders} * {months})", "rides/rider-month")["data"]["value"]
    weekly = run_sql(weekly_sql(prices))
    per_rider = run_sql(per_rider_sql(prices, months))
    dq = run_sql(DataCaveatsSQL)
    if dq.get("success"):
        q = dq["data"]["rows"][0]
        if q["non_positive_durations"]:
            caveats.append(f"{q['non_positive_durations']} trip(s) with zero/negative duration were excluded.")
        if q["over_24h"]:
            caveats.append(f"{q['over_24h']} trip(s) longer than 24 h kept as recorded (likely unreturned bikes).")
        if q["other_bike_types"]:
            caveats.append(f"{q['other_bike_types']} trip(s) of another rideable_type priced as classic.")
    decision = "Buy Monthly Membership" if mt < payg_total else "Pay Per Ride/Minute"
    return {
        "ok": True, "decision": decision, "rides": row["rides"], "riders": riders,
        "avg_duration_min": row["avg_duration_min"], "ebike_rides": row["ebike_rides"],
        "rides_over_free_minutes": row["rides_over_free_minutes"],
        "period": {"first_ride": row["first_ride"], "last_ride": row["last_ride"],
                   "days": row["days_covered"], "membership_months_per_rider": months},
        "payg_total": round(payg_total, 2),
        "membership_fees": round(riders * months * prices.monthly, 2),
        "member_residual": round(float(row["member_residual_total"]), 2),
        "membership_total": round(mt, 2),
        "difference": round(abs(mt - payg_total), 2),
        "payg_per_ride": round(per_ride_payg, 2),
        "break_even_rides_per_rider_month": round(break_even, 1) if break_even else None,
        "actual_rides_per_rider_month": round(actual, 1),
        "per_rider": per_rider["data"]["rows"][0] if per_rider.get("success") else None,
        "weekly": weekly["data"]["rows"] if weekly.get("success") else [],
        "caveats": caveats,
    }
