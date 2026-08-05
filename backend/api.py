import os
import uuid
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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
from backend.microapp import router as microapp_router


DEFAULT_WORKERS = 12
DEFAULT_TIMEOUT = 15
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
UPLOAD_MAGIC_BYTES = {
    ".xlsx": (b"PK\x03\x04",),
    ".xls": (b"\xd0\xcf\x11\xe0",),
}

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

# Mounted twice (bare + /api/ prefix) like every other route in this file --
# Vercel routes /api/* here, local uvicorn serves without that prefix.
app.include_router(microapp_router)
app.include_router(microapp_router, prefix="/api")

JOBS = {}


def require_api_key(x_api_key: str | None = Header(default=None)):
    expected = os.getenv("LEADSEASON_API_KEY", "")
    if not expected:
        # No key configured: auth is a no-op locally, but every write endpoint stays
        # unprotected until LEADSEASON_API_KEY is set — required before any public deploy.
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Nieprawidłowy lub brakujący X-API-Key.")


LANDING_HTML = """
<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LeadSeason API</title>
  <style>
    :root { color-scheme: dark; --bg:#070a11; --panel:#111827; --text:#fff7ed; --muted:#cbd5e1; --accent:#fb923c; --border:rgba(251,146,60,.34); }
    body { margin:0; min-height:100vh; font-family:Inter,Segoe UI,Arial,sans-serif; background:radial-gradient(circle at 20% 0%, rgba(251,146,60,.16), transparent 32%), var(--bg); color:var(--text); display:grid; place-items:center; }
    main { width:min(920px, calc(100vw - 32px)); border:1px solid var(--border); border-radius:14px; background:linear-gradient(135deg, rgba(17,24,39,.96), rgba(5,7,12,.94)); padding:28px; box-shadow:0 18px 50px rgba(0,0,0,.35); }
    .kicker { color:var(--accent); text-transform:uppercase; letter-spacing:.08em; font-size:12px; font-weight:800; }
    h1 { margin:8px 0 10px; font-size:32px; line-height:1.08; }
    p { color:var(--muted); line-height:1.55; margin:0 0 18px; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:10px; margin-top:18px; }
    a { color:var(--text); text-decoration:none; border:1px solid rgba(255,255,255,.12); border-radius:10px; padding:14px; background:rgba(255,255,255,.04); display:block; }
    a:hover { border-color:var(--accent); background:rgba(251,146,60,.10); }
    strong { display:block; margin-bottom:4px; }
    span { color:var(--muted); font-size:13px; }
    .note { margin-top:18px; padding:12px 14px; border-left:3px solid var(--accent); background:rgba(251,146,60,.10); border-radius:8px; }
  </style>
</head>
<body>
  <main>
    <div class="kicker">LeadSeason</div>
    <h1>API działa. Pełny dashboard Streamlit działa lokalnie.</h1>
    <p>Ten adres na Vercelu wystawia backend LeadSeason. Lokalna aplikacja operacyjna z dashboardem, Q4 i importem plików działa pod <strong>http://localhost:8510</strong>.</p>
    <div class="grid">
      <a href="/health"><strong>Status API</strong><span>Sprawdzenie działania backendu.</span></a>
      <a href="/docs"><strong>Dokumentacja API</strong><span>OpenAPI / Swagger.</span></a>
      <a href="/outputs"><strong>Pliki output</strong><span>Lista plików dostępnych na backendzie.</span></a>
      <a href="/q4/summary"><strong>Q4 summary</strong><span>Podsumowanie kolejki Q4, jeśli output jest dostępny.</span></a>
      <a href="/q4/actions"><strong>Q4 actions JSON</strong><span>Lista klientów/domen do działań.</span></a>
      <a href="/q4/actions.xlsx"><strong>Q4 XLSX</strong><span>Pobranie pliku akcyjnego.</span></a>
    </div>
    <div class="note">Jeśli oczekujesz pełnego UI w przeglądarce publicznie, trzeba zrobić osobny frontend webowy albo hostować Streamlit na środowisku, które obsługuje długotrwały proces Python.</div>
  </main>
</body>
</html>
"""


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


@app.get("/", response_class=HTMLResponse)
@app.get("/api", response_class=HTMLResponse)
@app.get("/api/", response_class=HTMLResponse)
def landing():
    return LANDING_HTML


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "OK", "service": "LeadSeason API"}


@app.get("/outputs")
@app.get("/api/outputs")
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
@app.get("/api/dashboard/summary")
def get_dashboard_summary(file: str | None = Query(default=None)):
    try:
        path = safe_output_path(file) if file else None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Nie ma takiego pliku output.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return dashboard_summary(path)


@app.get("/q4/summary")
@app.get("/api/q4/summary")
def get_q4_summary(file: str | None = Query(default=None)):
    try:
        path = safe_output_path(file) if file else None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Nie ma takiego pliku output.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return q4_summary(path)


@app.get("/q4/actions")
@app.get("/api/q4/actions")
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
@app.get("/api/q4/actions.xlsx")
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


async def _read_upload_capped(file: UploadFile, max_bytes: int) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Plik przekracza limit {max_bytes // (1024 * 1024)} MB.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_upload_content(suffix: str, content: bytes):
    if not content:
        raise HTTPException(status_code=400, detail="Plik jest pusty.")
    magic = UPLOAD_MAGIC_BYTES.get(suffix)
    if magic and not content.startswith(magic):
        raise HTTPException(status_code=400, detail=f"Zawartość pliku nie wygląda na prawidłowy {suffix.lstrip('.').upper()}.")
    if suffix == ".xml" and not content.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
        raise HTTPException(status_code=400, detail="Zawartość pliku nie wygląda na prawidłowy XML.")


@app.post("/uploads", dependencies=[Depends(require_api_key)])
@app.post("/api/uploads", dependencies=[Depends(require_api_key)])
async def upload_input(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".xlsx", ".xls", ".csv", ".xml"}:
        raise HTTPException(status_code=400, detail="Obsługiwane formaty: XLSX, XLS, CSV, XML.")
    content = await _read_upload_capped(file, MAX_UPLOAD_BYTES)
    _validate_upload_content(suffix, content)
    UPLOAD_DIR.mkdir(exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{Path(file.filename).name}"
    target = UPLOAD_DIR / safe_name
    target.write_bytes(content)
    return {"name": file.filename, "stored_as": str(target.relative_to(BASE_DIR)), "size": target.stat().st_size}


@app.post("/crawl/jobs", dependencies=[Depends(require_api_key)])
@app.post("/api/crawl/jobs", dependencies=[Depends(require_api_key)])
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
@app.get("/api/crawl/jobs/{job_id}")
def get_crawl_job(job_id: str):
    job = _load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Nie ma takiego joba.")
    return job
