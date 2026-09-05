from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import uuid
import shutil
import json

from services.pipeline import process_video, render_custom_clips
from services.llm_providers.factory import list_available_providers, get_llm_provider
from services.youtube_service import YouTubeService
from database import (
    init_db, create_job, get_job, get_all_jobs, update_job,
    save_youtube_config, get_youtube_config, save_youtube_token,
    get_youtube_token, delete_youtube_token, record_published_video,
    get_published_videos,
)

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


# ─── YouTube Channel Linking & 1-Click Publishing Endpoints ───────────────────

class YouTubeConfigRequest(BaseModel):
    client_id: str
    client_secret: str
    redirect_uri: Optional[str] = None


class YouTubePublishRequest(BaseModel):
    clip_path: str
    title: str
    description: Optional[str] = ""
    tags: Optional[List[str]] = []
    privacy_status: Optional[str] = "public"
    job_id: Optional[str] = None


@app.get("/api/youtube/status")
def get_youtube_status():
    cfg = get_youtube_config()
    token_info = get_youtube_token()
    client_id = cfg.get("client_id", "")

    return {
        "configured": bool(client_id and cfg.get("client_secret")),
        "client_id_preview": (client_id[:16] + "...") if client_id else "",
        "redirect_uri": cfg.get("redirect_uri", "http://localhost:8000/api/youtube/callback"),
        "connected": token_info is not None,
        "channel": {
            "id": token_info["channel_id"],
            "title": token_info["channel_title"],
            "avatar": token_info["channel_avatar"],
        } if token_info else None
    }


@app.post("/api/youtube/configure")
def configure_youtube(payload: YouTubeConfigRequest):
    if not payload.client_id or not payload.client_secret:
        raise HTTPException(status_code=400, detail="client_id and client_secret are required")
    save_youtube_config(payload.client_id.strip(), payload.client_secret.strip(), payload.redirect_uri)
    return {"status": "saved", "message": "YouTube OAuth credentials updated."}


@app.get("/api/youtube/auth-url")
def get_youtube_auth_url():
    cfg = get_youtube_config()
    client_id = cfg.get("client_id")
    redirect_uri = cfg.get("redirect_uri", "http://localhost:8000/api/youtube/callback")

    if not client_id:
        raise HTTPException(status_code=400, detail="YouTube OAuth Client ID is not configured yet. Please configure it in settings.")

    auth_url = YouTubeService.get_auth_url(client_id, redirect_uri)
    return {"auth_url": auth_url}


@app.get("/api/youtube/callback", response_class=HTMLResponse)
def youtube_oauth_callback(code: Optional[str] = None, error: Optional[str] = None):
    if error:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family:sans-serif; background:#0f172a; color:#f87171; padding:40px; text-align:center;">
          <h2>Authorization Failed</h2>
          <p>{error}</p>
          <button onclick="window.close()" style="background:#334155; color:#fff; border:none; padding:10px 20px; border-radius:8px; cursor:pointer;">Close Window</button>
        </body>
        </html>
        """)

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code from Google")

    cfg = get_youtube_config()
    client_id = cfg.get("client_id")
    client_secret = cfg.get("client_secret")
    redirect_uri = cfg.get("redirect_uri", "http://localhost:8000/api/youtube/callback")

    try:
        token_data = YouTubeService.exchange_code(code, client_id, client_secret, redirect_uri)
        channel_info = YouTubeService.get_channel_profile(token_data["access_token"])

        save_youtube_token(
            channel_id=channel_info["channel_id"],
            channel_title=channel_info["title"],
            channel_avatar=channel_info["avatar"],
            token_data=token_data,
        )

        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><title>YouTube Connected</title></head>
        <body style="font-family:system-ui,sans-serif; background:#020617; color:#fff; display:flex; align-items:center; justify-content:center; height:100vh; margin:0;">
          <div style="background:#0f172a; border:1px solid #334155; border-radius:24px; padding:32px; text-align:center; max-width:400px; box-shadow:0 0 40px rgba(99,102,241,0.2);">
            <img src="{channel_info['avatar']}" style="width:64px; height:64px; border-radius:50%; border:2px solid #818cf8; margin-bottom:16px;" onerror="this.style.display='none'"/>
            <h2 style="margin:0 0 8px 0; color:#f8fafc;">Channel Connected!</h2>
            <p style="color:#94a3b8; font-size:14px; margin:0 0 20px 0;"><b>{channel_info['title']}</b> is now linked to Auto Shorts.</p>
            <p style="color:#64748b; font-size:12px;">This popup will close automatically...</p>
          </div>
          <script>
            try {{
              if (window.opener) {{
                window.opener.postMessage({{ type: 'YOUTUBE_AUTH_SUCCESS', channel: {json.dumps(channel_info)} }}, '*');
                setTimeout(() => window.close(), 1200);
              }} else {{
                setTimeout(() => window.location.href = '/', 1500);
              }}
            }} catch (e) {{
              setTimeout(() => window.close(), 2000);
            }}
          </script>
        </body>
        </html>
        """)
    except Exception as e:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family:sans-serif; background:#0f172a; color:#f87171; padding:40px; text-align:center;">
          <h2>Connection Error</h2>
          <p>{str(e)}</p>
          <button onclick="window.close()" style="background:#334155; color:#fff; border:none; padding:10px 20px; border-radius:8px; cursor:pointer;">Close Window</button>
        </body>
        </html>
        """)


@app.post("/api/youtube/disconnect")
def disconnect_youtube():
    delete_youtube_token()
    return {"status": "disconnected", "message": "YouTube channel unlinked."}


@app.post("/api/youtube/publish")
def publish_short_to_youtube(payload: YouTubePublishRequest):
    token_row = get_youtube_token()
    if not token_row:
        raise HTTPException(status_code=400, detail="No linked YouTube channel. Please connect your YouTube account first.")

    cfg = get_youtube_config()
    client_id = cfg.get("client_id")
    client_secret = cfg.get("client_secret")

    # Resolve video path
    raw_path = payload.clip_path.replace('\\', '/')
    candidates = [
        raw_path,
        os.path.join(OUTPUT_DIR, os.path.basename(raw_path)),
        os.path.abspath(raw_path),
    ]
    if raw_path.startswith("output/"):
        candidates.append(raw_path)
    elif "/output/" in raw_path:
        candidates.append(raw_path.split("/output/")[-1])
        candidates.append("output/" + raw_path.split("/output/")[-1])

    actual_file = None
    for cand in candidates:
        if cand and os.path.exists(cand) and os.path.isfile(cand):
            actual_file = cand
            break

    if not actual_file:
        raise HTTPException(status_code=404, detail=f"Video file not found at path: {payload.clip_path}")

    try:
        result = YouTubeService.upload_short(
            video_path=actual_file,
            title=payload.title,
            description=payload.description or "",
            tags=payload.tags or ["Shorts"],
            privacy_status=payload.privacy_status or "public",
            token_data=token_row["token"],
            client_id=client_id,
            client_secret=client_secret,
        )

        record_published_video(
            job_id=payload.job_id or "",
            clip_path=payload.clip_path,
            youtube_video_id=result["video_id"],
            youtube_url=result["youtube_url"],
            title=result["title"],
            description=payload.description or "",
            privacy_status=result["privacy_status"],
        )

        return result
    except Exception as e:
        print(f"[YouTube Publish Error] {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/youtube/published")
def get_published(job_id: Optional[str] = None):
    return get_published_videos(job_id)

