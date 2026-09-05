from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import uuid
import shutil

from services.pipeline import process_video, render_custom_clips
from services.llm_providers.factory import list_available_providers, get_llm_provider
from database import init_db, create_job, get_job, get_all_jobs, update_job

app = FastAPI(title="Auto Shorts API")

# Allow CORS for local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Serve output directory for previews and completed videos
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")

# Initialize SQLite DB
init_db()


class RenderRequest(BaseModel):
    job_id: str
    clips: List[Dict[str, Any]]
    font: Optional[str] = "Montserrat-Black.ttf"
    destinations: Optional[str] = "TikTok"


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Auto Shorts API running"}


@app.get("/api/providers")
def get_providers():
    """List available LLM providers and active provider."""
    return {
        "providers": list_available_providers(),
        "active": get_llm_provider().provider_name,
    }


class SocialKitRequest(BaseModel):
    title: str
    transcript_segment: str


@app.get("/api/gemini/status")
def get_gemini_status():
    from services.llm_providers.gemini_provider import GeminiProvider
    gemini = GeminiProvider()
    return {
        "available": gemini.is_available(),
        "provider": gemini.provider_name,
        "active_model": os.getenv("GEMINI_MODEL", "gemini-3.7-flash"),
        "fallback_models": gemini.models,
    }


@app.post("/api/generate-social-kit")
def generate_social_kit(payload: SocialKitRequest):
    from services.llm_providers.gemini_provider import GeminiProvider
    gemini = GeminiProvider()
    if not gemini.is_available():
        raise HTTPException(status_code=503, detail="Gemini API is not configured or unavailable")
    kit = gemini.generate_social_kit(payload.transcript_segment, payload.title)
    if not kit:
        raise HTTPException(status_code=500, detail="Failed to generate social media kit")
    return kit


@app.post("/api/upload")
@app.post("/api/analyze")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    transcript: UploadFile = File(None),
    font: str = Form("Montserrat-Black.ttf"),
    destinations: str = Form("TikTok"),
    num_clips: int = Form(3),
    auto_render: bool = Form(False),
    custom_prompt: Optional[str] = Form(None),
):
    if not file.filename.endswith(('.mp4', '.mov', '.mkv')):
        raise HTTPException(status_code=400, detail="Invalid file type")

    job_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}_{file.filename}")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    transcript_path = None
    if transcript and transcript.filename:
        transcript_path = os.path.join(UPLOAD_DIR, f"{job_id}_{transcript.filename}")
        with open(transcript_path, "wb") as buffer:
            shutil.copyfileobj(transcript.file, buffer)

    num_clips = max(1, min(num_clips, 5))
    create_job(job_id, file.filename, "processing", 0, "Video uploaded, analyzing audio and speech...")

    background_tasks.add_task(
        process_video,
        job_id,
        file_path,
        file.filename,
        font,
        destinations,
        transcript_path,
        num_clips,
        auto_render,
        custom_prompt,
    )

    return {
        "job_id": job_id,
        "message": "Upload successful, multi-modal hook analysis started.",
    }


@app.post("/api/render")
async def render_clips(
    payload: RenderRequest,
    background_tasks: BackgroundTasks,
):
    job = get_job(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not payload.clips:
        raise HTTPException(status_code=400, detail="No clips provided for rendering")

    update_job(
        payload.job_id,
        status="queued_for_render",
        progress=72,
        message="Queued customized clips for rendering...",
    )

    background_tasks.add_task(
        render_custom_clips,
        payload.job_id,
        payload.clips,
        payload.font or "Montserrat-Black.ttf",
        payload.destinations or "TikTok",
    )

    return {
        "job_id": payload.job_id,
        "message": f"Rendering {len(payload.clips)} short(s) queued.",
    }


@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs")
def list_jobs():
    return get_all_jobs()
