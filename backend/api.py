import os
import uuid
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.data_service import (
    BASE_DIR,
    JOBS_DIR,
    OUTPUT_DIR,
    UPLOAD_DIR,
    dashboard_summary,
    default_output_file,
    output_files,
    q4_action_frame,
    q4_summary,
    safe_input_path,
    safe_output_path,
)


DEFAULT_WORKERS = 12
DEFAULT_TIMEOUT = 15

app = FastAPI(
    title="LeadSeason API",
    version="0.1.0",
    description="Backend API dla pipeline'u LeadSeason: dane, crawl, Q4 action base i integracje.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8510", "http://127.0.0.1:8510"],
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS = {}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _job_path(job_id):
    JOBS_DIR.mkdir(exist_ok=True)
    return JOBS_DIR / f"{job_id}.json"


def _save_job(job_id, data):
    JOBS[job_id] = data
    path = _job_path(job_id)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=JOBS_DIR, suffix=".tmp") as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _load_job(job_id):
    if job_id in JOBS:
        return JOBS[job_id]
    path = _job_path(job_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    JOBS[job_id] = data
    return data


class CrawlRequest(BaseModel):
    input_path: str = Field(..., description="Ścieżka do XLSX/CSV/XML względem projektu albo absolutna.")
    output_name: str = "leadseason_api_crawl.xlsx"
    limit: int = 0
    workers: int = DEFAULT_WORKERS
    timeout: int = DEFAULT_TIMEOUT
    force: bool = False
    use_places: bool = False


def _run_crawl_job(job_id, request):
    job = _load_job(job_id) or {"id": job_id}
    job.update({"status": "RUNNING", "started_at": _now_iso()})
    _save_job(job_id, job)
    try:
        from bulk_crawler import run_bulk

        input_path = safe_input_path(request.input_path)
        OUTPUT_DIR.mkdir(exist_ok=True)
        output_path = OUTPUT_DIR / Path(request.output_name).name
        rows = run_bulk(
            input_xml=input_path,
            output_path=output_path,
            cache_dir=BASE_DIR / "cache" / "domains",
            workers=request.workers,
            timeout=request.timeout,
            force=request.force,
            limit=request.limit,
            use_places=request.use_places,
            places_api_key=os.getenv("GOOGLE_PLACES_API_KEY", ""),
            places_cache_dir=BASE_DIR / "cache" / "places",
        )
        job.update({
            "status": "DONE",
            "records": len(rows),
            "output": str(output_path),
            "output_name": output_path.name,
            "finished_at": _now_iso(),
        })
        _save_job(job_id, job)
    except Exception as exc:
        job.update({"status": "ERROR", "error": str(exc), "finished_at": _now_iso()})
        _save_job(job_id, job)


@app.get("/health")
def health():
    return {"status": "OK", "service": "LeadSeason API"}


@app.get("/outputs")
def outputs():
    return [
        {
            "name": path.name,
            "size_mb": round(path.stat().st_size / 1024 / 1024, 2),
            "modified": path.stat().st_mtime,
            "default": path == default_output_file(),
        }
        for path in output_files()
    ]


@app.get("/dashboard/summary")
def get_dashboard_summary(file: str | None = Query(default=None)):
    try:
        path = safe_output_path(file) if file else None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Nie ma takiego pliku output.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return dashboard_summary(path)


@app.get("/q4/summary")
def get_q4_summary(file: str | None = Query(default=None)):
    try:
        path = safe_output_path(file) if file else None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Nie ma takiego pliku output.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return q4_summary(path)


@app.get("/q4/actions")
def get_q4_actions(
    file: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=5000),
):
    try:
        path = safe_output_path(file) if file else None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Nie ma takiego pliku output.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    frame = q4_action_frame(path).head(limit)
    return JSONResponse(frame.fillna("").to_dict(orient="records"))


@app.get("/q4/actions.xlsx")
def download_q4_actions(file: str | None = Query(default=None)):
    try:
        path = safe_output_path(file) if file else None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Nie ma takiego pliku output.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    frame = q4_action_frame(path)
    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / "leadseason_api_q4_actions.xlsx"
    frame.to_excel(output_path, index=False)
    return FileResponse(
        output_path,
        filename=output_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/uploads")
async def upload_input(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".xlsx", ".xls", ".csv", ".xml"}:
        raise HTTPException(status_code=400, detail="Obsługiwane formaty: XLSX, XLS, CSV, XML.")
    UPLOAD_DIR.mkdir(exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{Path(file.filename).name}"
    target = UPLOAD_DIR / safe_name
    target.write_bytes(await file.read())
    return {"name": file.filename, "stored_as": str(target.relative_to(BASE_DIR)), "size": target.stat().st_size}


@app.post("/crawl/jobs")
def create_crawl_job(request: CrawlRequest, background_tasks: BackgroundTasks):
    try:
        safe_input_path(request.input_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    job_id = uuid.uuid4().hex
    _save_job(job_id, {"id": job_id, "status": "QUEUED", "created_at": _now_iso(), "request": request.model_dump()})
    background_tasks.add_task(_run_crawl_job, job_id, request)
    return _load_job(job_id)


@app.get("/crawl/jobs/{job_id}")
def get_crawl_job(job_id: str):
    job = _load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Nie ma takiego joba.")
    return job
