"""HW7 Part 4 - build the two acceptance-case CSVs from REAL Bay Wheels trip data.

    python code/bikeshare/prepare_scenarios.py                 # default month 202509
    python code/bikeshare/prepare_scenarios.py --month 202508
    python code/bikeshare/prepare_scenarios.py --zip ~/Downloads/202509-baywheels-tripdata.csv.zip

Source: Bay Wheels system data (https://www.lyft.com/bikes/bay-wheels/system-data), monthly
files at https://s3.amazonaws.com/baywheels-data/<YYYYMM>-baywheels-tripdata.csv.zip.

The public data has no rider identifier, so each scenario samples real trips (real
timestamps, durations, bike types, stations) from the first 28 days of the month and
assigns them to rider_id values with SEED 1346 (stated as an assumption in every report):

  membership_wins  540 member trips of 10-45 min -> 15 riders x 36 rides  (many / longer rides)
  payg_wins        520 casual trips of 3-12 min   -> 260 riders x 2 rides  (few / short rides)

Output: reports/hw07/cases/bike/<scenario>.csv and reports/hw07/raw/bike_scenario_summaries.json
"""
import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hw07_config as cfg  # noqa: E402

DATA_DIR = cfg.REPO_ROOT / "data" / "baywheels"            # gitignored download cache
OUT_DIR = cfg.CASES_DIR / "bike"
URL = "https://s3.amazonaws.com/baywheels-data/{month}-baywheels-tripdata.csv.zip"
KEEP = ["ride_id", "rideable_type", "started_at", "ended_at", "start_station_name", "end_station_name",
        "start_lat", "start_lng", "end_lat", "end_lng", "member_casual"]
SCENARIOS = {
    "membership_wins": {"member_casual": "member", "min_minutes": 10, "max_minutes": 45,
                        "ebike_share": None, "trips": 540, "riders": 15},
    "payg_wins": {"member_casual": "casual", "min_minutes": 3, "max_minutes": 12,
                  "ebike_share": 0.15, "trips": 520, "riders": 260},
}


def download(month: str) -> Path:
    """Fetch the monthly zip once (cached under data/baywheels/)."""
    import httpx
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{month}-baywheels-tripdata.csv.zip"
    if path.exists() and path.stat().st_size > 0:
        return path
    url = URL.format(month=month)
    print(f"downloading {url} ...")
    with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        with open(path, "wb") as fh:
            for chunk in r.iter_bytes():
                fh.write(chunk)
    return path


def load(zip_path: Path) -> pd.DataFrame:
    """Read the CSV inside the zip and add duration_min."""
    with zipfile.ZipFile(zip_path) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".csv") and not n.startswith("__MACOSX"))
        df = pd.read_csv(io.BytesIO(zf.read(name)), low_memory=False)
    df = df[[c for c in KEEP if c in df.columns]].copy()
    df["started_at"] = pd.to_datetime(df["started_at"], errors="coerce")
    df["ended_at"] = pd.to_datetime(df["ended_at"], errors="coerce")
    df = df.dropna(subset=["started_at", "ended_at"])
    df["duration_min"] = (df["ended_at"] - df["started_at"]).dt.total_seconds() / 60
    return df


def build(df: pd.DataFrame, name: str, spec: dict) -> tuple[pd.DataFrame, dict]:
    """Filter, sample and assign riders for one scenario."""
    start = df["started_at"].min().normalize()
    window = df[(df["started_at"] >= start) & (df["started_at"] < start + pd.Timedelta(days=28))]
    pool = window[(window["member_casual"] == spec["member_casual"])
                  & window["duration_min"].between(spec["min_minutes"], spec["max_minutes"])
                  & window["rideable_type"].isin(["classic_bike", "electric_bike"])]
    if spec["ebike_share"] is not None:
        n_e = round(spec["trips"] * spec["ebike_share"])
        e = pool[pool["rideable_type"] == "electric_bike"].sample(n=n_e, random_state=cfg.SEED)
        c = pool[pool["rideable_type"] == "classic_bike"].sample(n=spec["trips"] - n_e, random_state=cfg.SEED)
        sample = pd.concat([e, c])
    else:
        sample = pool.sample(n=spec["trips"], random_state=cfg.SEED)
    sample = sample.sample(frac=1, random_state=cfg.SEED).reset_index(drop=True)
    sample["rider_id"] = [f"R{(i % spec['riders']) + 1:03d}" for i in range(len(sample))]
    sample = sample.sort_values("started_at")
    out = sample.drop(columns=["duration_min"]).copy()
    for col in ("started_at", "ended_at"):
        out[col] = out[col].dt.strftime("%Y-%m-%d %H:%M:%S")
    summary = {
        "scenario": name, "rows": len(out), "riders": spec["riders"], "filters": spec,
        "pool_size": len(pool), "window": [str(start.date()), str((start + pd.Timedelta(days=27)).date())],
        "avg_duration_min": round(float(sample["duration_min"].mean()), 2),
        "median_duration_min": round(float(sample["duration_min"].median()), 2),
        "ebike_share": round(float((sample["rideable_type"] == "electric_bike").mean()), 3),
        "rides_per_rider": spec["trips"] / spec["riders"],
        "first_ride": str(sample["started_at"].min()), "last_ride": str(sample["started_at"].max()),
    }
    return out, summary


def main() -> None:
    """Download (or read) one month and write both scenario CSVs + summaries."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default="202509")
    ap.add_argument("--zip", default=None, help="use an already downloaded zip")
    a = ap.parse_args()
    zip_path = Path(a.zip).expanduser() if a.zip else download(a.month)
    df = load(zip_path)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg.ensure_dirs()
    summaries = {"source_url": URL.format(month=a.month), "source_page": "https://www.lyft.com/bikes/bay-wheels/system-data",
                 "zip_file": zip_path.name, "zip_sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
                 "month_rows": len(df), "seed": cfg.SEED, "prepared_at": cfg.now_iso(),
                 "rider_id_note": "Public data has no rider id; trips are assigned to riders with SEED.",
                 "scenarios": {}}
    for name, spec in SCENARIOS.items():
        out, summary = build(df, name, spec)
        path = OUT_DIR / f"{name}.csv"
        out.to_csv(path, index=False)
        summary["csv"] = str(path.relative_to(cfg.REPO_ROOT))
        summary["csv_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        summaries["scenarios"][name] = summary
        print(f"{name}: {summary['rows']} trips, {summary['riders']} riders, avg {summary['avg_duration_min']} min, "
              f"ebike share {summary['ebike_share']} -> {summary['csv']}")
    (cfg.RAW_DIR / "bike_scenario_summaries.json").write_text(json.dumps(summaries, indent=2))
    print("summary: reports/hw07/raw/bike_scenario_summaries.json")


if __name__ == "__main__":
    main()
