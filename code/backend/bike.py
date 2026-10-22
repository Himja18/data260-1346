"""HW7 Part 4 - FastAPI route behind the Bike Share Advisor page.

POST /api/bike/run   multipart form: trips_csv (file), pricing_url, scenario,
                     prompt_defense, tool_defense  -> full advisor result (timeline, costs,
                     decision, citations, metrics). Any authenticated role may run it.
GET  /api/bike/fixtures/{name}   serves the local hostile pricing fixtures (Part 5) so the UI
                     can point the pricing URL at them; only files in reports/hw07/cases/hostile.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from auth import READ_ROLES, require_roles

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

import hw07_config as cfg  # noqa: E402
from bikeshare.agent import BAY_WHEELS_PRICING_URL, BikeRunConfig, run_bike_agent, run_log_block  # noqa: E402
from bikeshare.tools import SecurityConfig  # noqa: E402

router = APIRouter(prefix="/api/bike", tags=["HW7 Part 4 - bike share advisor"])
FIXTURE_DIR = cfg.CASES_DIR / "hostile"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
OBS_CHARS = 1200


def _trim(result: dict) -> dict:
    """Keep the response small: shorten each observation for the timeline panel."""
    out = dict(result)
    out["timeline"] = []
    for t in result.get("timeline", []):
        t = dict(t)
        obs = json.dumps(t.get("observation"), default=str)
        t["observation"] = obs if len(obs) <= OBS_CHARS else obs[:OBS_CHARS] + " ..."
        out["timeline"].append(t)
    return out


@router.post("/run", dependencies=[Depends(require_roles(*READ_ROLES))])
async def run(trips_csv: UploadFile = File(...), pricing_url: str = Form(BAY_WHEELS_PRICING_URL),
              scenario: str = Form("adhoc"), prompt_defense: bool = Form(True),
              tool_defense: bool = Form(True)) -> dict:
    """Run the ReAct/MRKL advisor on an uploaded CSV and a pricing URL."""
    if not (trips_csv.filename or "").lower().endswith(".csv"):
        raise HTTPException(422, detail="trips_csv must be a .csv file")
    scenario = "".join(ch for ch in scenario if ch.isalnum() or ch in "_-")[:40] or "adhoc"
    tmp = Path(tempfile.mkdtemp(prefix="s1346_bike_"))
    path = tmp / "uploaded.csv"
    with open(path, "wb") as fh:
        shutil.copyfileobj(trips_csv.file, fh, length=1024 * 1024)
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail="CSV larger than 20 MB")
    url = pricing_url.strip()
    if url.startswith("fixture:"):                       # UI shortcut for the Part 5 fixtures
        url = str((FIXTURE_DIR / Path(url.removeprefix("fixture:")).name).resolve())
    conf = BikeRunConfig(csv_path=str(path), pricing_url=url, scenario=scenario,
                         security=SecurityConfig(prompt_defense, tool_defense))
    result = await run_in_threadpool(run_bike_agent, conf)
    cfg.ensure_dirs()
    with open(cfg.RUN_LOG, "a", encoding="utf-8") as fh:
        fh.write(f"\n{'=' * 78}\nHW7 PART 4 - advisor run from the UI ({cfg.now_iso()}, {cfg.STUDENT_NAME})\n")
        fh.write(run_log_block(result))
    if scenario in ("membership_wins", "payg_wins") and prompt_defense and tool_defense:
        from run_hw07_part4 import save_evidence
        save_evidence(result, scenario)
    shutil.rmtree(tmp, ignore_errors=True)
    return _trim(result)


@router.get("/fixtures/{name}")
def fixture(name: str) -> FileResponse:
    """Serve a local hostile fixture (name only - no paths)."""
    path = (FIXTURE_DIR / Path(name).name).resolve()
    if path.parent != FIXTURE_DIR.resolve() or not path.exists():
        raise HTTPException(404, detail="fixture not found")
    return FileResponse(path, media_type="text/html")
