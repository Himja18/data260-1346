"""HW7 Part 4 runner - the two acceptance cases from the command line (the UI does the same).

    python code/run_hw07_part4.py --check-pricing            # fetch + show extracted prices
    python code/run_hw07_part4.py --scenario membership_wins
    python code/run_hw07_part4.py --scenario payg_wins
    python code/run_hw07_part4.py --scenario both

Evidence per scenario (reports/hw07/raw/):
  pricing_snapshots/<scenario>/pricing_snapshot.txt   exact page text used
  pricing_snapshots/<scenario>/pricing_snapshot.json  url, final url, access time, SHA-256
  part4_<scenario>_result.json                         full result incl. timeline
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hw07_config as cfg  # noqa: E402
from bikeshare.agent import BAY_WHEELS_PRICING_URL, BikeRunConfig, run_bike_agent, run_log_block  # noqa: E402
from bikeshare.pricing import extract_prices  # noqa: E402
from bikeshare.tools import SecurityConfig, fetch_snapshot  # noqa: E402

SCENARIO_CSV = {s: cfg.CASES_DIR / "bike" / f"{s}.csv" for s in ("membership_wins", "payg_wins")}


def save_evidence(result: dict, scenario: str) -> None:
    """Copy the snapshot + result into reports/hw07/raw for the write-up."""
    src = Path(result["out_dir"])
    dst = cfg.RAW_DIR / "pricing_snapshots" / scenario
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("pricing_snapshot.txt", "pricing_snapshot.json"):
        if (src / name).exists():
            shutil.copyfile(src / name, dst / name)
    slim = {k: v for k, v in result.items() if k != "timeline"}
    slim["timeline"] = [{k: v for k, v in t.items() if k != "observation"} for t in result["timeline"]]
    (cfg.RAW_DIR / f"part4_{scenario}_result.json").write_text(json.dumps(result, indent=2, default=str))
    (cfg.RAW_DIR / f"part4_{scenario}_summary.json").write_text(json.dumps(slim, indent=2, default=str))


def print_result(r: dict) -> None:
    """Human-readable summary (mirrored into RUN_LOG.txt)."""
    print(run_log_block(r))
    c = r.get("computed", {})
    if c.get("ok"):
        print(f"COST COMPARISON  pay-per-use ${c['payg_total']:.2f} | membership ${c['membership_total']:.2f} "
              f"(fees ${c['membership_fees']:.2f} + residual ${c['member_residual']:.2f}) | "
              f"break-even {c['break_even_rides_per_rider_month']} rides/rider-month vs actual "
              f"{c['actual_rides_per_rider_month']}")
        print(f"{'week':<12}{'rides':>7}{'avg min':>9}{'payg $':>10}{'member resid $':>16}")
        for w in c["weekly"]:
            print(f"{w['week']:<12}{w['rides']:>7}{w['avg_duration_min']:>9}{w['payg_spend']:>10}"
                  f"{w['member_residual_spend']:>16}")
    else:
        print(f"COST COMPARISON unavailable: {c.get('error')}")


def main() -> None:
    """Parse flags; run scenarios or the pricing check."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=["membership_wins", "payg_wins", "both"])
    ap.add_argument("--pricing-url", default=BAY_WHEELS_PRICING_URL)
    ap.add_argument("--check-pricing", action="store_true")
    a = ap.parse_args()
    if a.check_pricing:
        snap = fetch_snapshot(a.pricing_url)
        p = extract_prices(snap.text)
        print(json.dumps(snap.meta(), indent=2))
        print(json.dumps({k: v for k, v in p.__dict__.items()}, indent=2))
        print("MISSING:", p.missing or "none - all prices found")
        return
    if not a.scenario:
        ap.error("--scenario or --check-pricing required")
    names = ["membership_wins", "payg_wins"] if a.scenario == "both" else [a.scenario]
    with cfg.run_log("HW7 PART 4 - Bay Wheels ReAct/MRKL advisor (CLI)"):
        for s in names:
            if not SCENARIO_CSV[s].exists():
                raise SystemExit(f"{SCENARIO_CSV[s]} missing - run code/bikeshare/prepare_scenarios.py first")
            print(f"--- scenario {s} ---")
            r = run_bike_agent(BikeRunConfig(csv_path=str(SCENARIO_CSV[s]), pricing_url=a.pricing_url,
                                             scenario=s, security=SecurityConfig(True, True)))
            save_evidence(r, s)
            print_result(r)


if __name__ == "__main__":
    main()
