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
from dotenv import load_dotenv

load_dotenv()

from services.pipeline import process_video, render_custom_clips
from services.llm_providers.factory import list_available_providers, get_llm_provider
from services.youtube_service import YouTubeService
from services.tiktok_service import TikTokService
from services.instagram_service import InstagramService
from database import (
    init_db, create_job, get_job, get_all_jobs, update_job,
    save_youtube_config, get_youtube_config, save_youtube_token,
    get_youtube_token, delete_youtube_token, record_published_video,
    get_published_videos,
    save_tiktok_config, get_tiktok_config, save_tiktok_token,
    get_tiktok_token, delete_tiktok_token,
    save_instagram_config, get_instagram_config, save_instagram_token,
    get_instagram_token, delete_instagram_token,
    record_social_post, get_social_posts,
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


def is_valid_google_client_id(cid: str) -> bool:
    if not cid or len(cid.strip()) < 15:
        return False
    clean = cid.strip()
    if clean.startswith("test-") or clean.startswith("your_"):
        return False
    return "apps.googleusercontent.com" in clean


@app.get("/api/youtube/status")
def get_youtube_status():
    cfg = get_youtube_config()
    token_info = get_youtube_token()
    client_id = cfg.get("client_id", "").strip()
    client_secret = cfg.get("client_secret", "").strip()

    is_configured = bool(client_id and client_secret) and is_valid_google_client_id(client_id)

    return {
        "configured": is_configured,
        "client_id": client_id if is_configured else "",
        "client_id_preview": (client_id[:16] + "...") if is_configured else "",
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
    client_id = cfg.get("client_id", "").strip()
    redirect_uri = cfg.get("redirect_uri", "http://localhost:8000/api/youtube/callback")

    if not is_valid_google_client_id(client_id):
        raise HTTPException(
            status_code=400,
            detail="A valid Google OAuth Client ID is required. Please configure your Client ID & Secret from Google Cloud Console."
        )

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


# ─── TikTok Account Linking & Publishing Endpoints ───────────────────────────

class TikTokConfigRequest(BaseModel):
    app_key:      str
    app_secret:   str
    redirect_uri: Optional[str] = None


class TikTokPublishRequest(BaseModel):
    clip_path:     str
    title:         str
    caption:       Optional[str] = ""
    privacy_level: Optional[str] = "PUBLIC_TO_EVERYONE"
    job_id:        Optional[str] = None


# In-memory PKCE verifier store (single-user desktop app; cleared after use)
_tiktok_pkce_store: Dict[str, str] = {}


@app.get("/api/tiktok/status")
def get_tiktok_status():
    cfg        = get_tiktok_config()
    token_info = get_tiktok_token()
    app_key    = cfg.get("app_key", "").strip()
    app_secret = cfg.get("app_secret", "").strip()
    configured = bool(app_key and app_secret and len(app_key) > 5)
    return {
        "configured":    configured,
        "app_key":       app_key if configured else "",
        "redirect_uri":  cfg.get("redirect_uri", "http://localhost:8000/api/tiktok/callback"),
        "connected":     token_info is not None,
        "account": {
            "open_id":      token_info["open_id"],
            "display_name": token_info["display_name"],
            "username":     token_info["username"],
            "avatar_url":   token_info["avatar_url"],
        } if token_info else None,
    }


@app.post("/api/tiktok/configure")
def configure_tiktok(payload: TikTokConfigRequest):
    if not payload.app_key or not payload.app_secret:
        raise HTTPException(status_code=400, detail="app_key and app_secret are required")
    save_tiktok_config(payload.app_key.strip(), payload.app_secret.strip(), payload.redirect_uri)
    return {"status": "saved", "message": "TikTok app credentials updated."}


@app.get("/api/tiktok/auth-url")
def get_tiktok_auth_url():
    cfg          = get_tiktok_config()
    app_key      = cfg.get("app_key", "").strip()
    redirect_uri = cfg.get("redirect_uri", "http://localhost:8000/api/tiktok/callback")
    if not app_key or len(app_key) < 5:
        raise HTTPException(
            status_code=400,
            detail="A valid TikTok App Key is required. Please configure your App Key & Secret from the TikTok Developer Portal."
        )
    code_verifier, _ = TikTokService.generate_pkce_pair()
    _tiktok_pkce_store["current"] = code_verifier
    auth_url = TikTokService.get_auth_url(app_key, redirect_uri, code_verifier)
    return {"auth_url": auth_url}


@app.get("/api/tiktok/callback", response_class=HTMLResponse)
def tiktok_oauth_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    if error:
        return HTMLResponse(f"""
        <!DOCTYPE html><html>
        <body style="font-family:sans-serif;background:#0f172a;color:#f87171;padding:40px;text-align:center;">
          <h2>TikTok Authorization Failed</h2><p>{error}</p>
          <button onclick="window.close()" style="background:#334155;color:#fff;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;">Close</button>
        </body></html>""")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code from TikTok")

    cfg          = get_tiktok_config()
    app_key      = cfg.get("app_key")
    app_secret   = cfg.get("app_secret")
    redirect_uri = cfg.get("redirect_uri", "http://localhost:8000/api/tiktok/callback")
    code_verifier = _tiktok_pkce_store.pop("current", "")

    try:
        token_data   = TikTokService.exchange_code(code, code_verifier, app_key, app_secret, redirect_uri)
        creator_info = TikTokService.get_creator_info(token_data["access_token"])

        save_tiktok_token(
            open_id=creator_info["open_id"],
            display_name=creator_info["display_name"],
            username=creator_info["username"],
            avatar_url=creator_info["avatar_url"],
            token_data=token_data,
        )

        account_json = json.dumps(creator_info)
        return HTMLResponse(f"""
        <!DOCTYPE html><html>
        <head><title>TikTok Connected</title></head>
        <body style="font-family:system-ui,sans-serif;background:#020617;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
          <div style="background:#0f172a;border:1px solid #334155;border-radius:24px;padding:32px;text-align:center;max-width:400px;box-shadow:0 0 40px rgba(0,0,0,0.5);">
            <div style="font-size:48px;margin-bottom:16px;">&#x266B;</div>
            <h2 style="margin:0 0 8px 0;color:#f8fafc;">TikTok Connected!</h2>
            <p style="color:#94a3b8;font-size:14px;margin:0 0 20px 0;"><b>@{creator_info['username'] or creator_info['display_name']}</b> is now linked to Auto Shorts.</p>
            <p style="color:#64748b;font-size:12px;">This popup will close automatically...</p>
          </div>
          <script>
            try {{
              if (window.opener) {{
                window.opener.postMessage({{ type: 'TIKTOK_AUTH_SUCCESS', account: {account_json} }}, '*');
                setTimeout(() => window.close(), 1200);
              }} else {{
                setTimeout(() => window.location.href = '/', 1500);
              }}
            }} catch (e) {{ setTimeout(() => window.close(), 2000); }}
          </script>
        </body></html>""")
    except Exception as e:
        return HTMLResponse(f"""
        <!DOCTYPE html><html>
        <body style="font-family:sans-serif;background:#0f172a;color:#f87171;padding:40px;text-align:center;">
          <h2>TikTok Connection Error</h2><p>{str(e)}</p>
          <button onclick="window.close()" style="background:#334155;color:#fff;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;">Close</button>
        </body></html>""")


@app.post("/api/tiktok/disconnect")
def disconnect_tiktok():
    delete_tiktok_token()
    return {"status": "disconnected", "message": "TikTok account unlinked."}


@app.post("/api/tiktok/publish")
def publish_to_tiktok(payload: TikTokPublishRequest):
    token_row = get_tiktok_token()
    if not token_row:
        raise HTTPException(status_code=400, detail="No linked TikTok account. Please connect your TikTok account first.")

    cfg        = get_tiktok_config()
    app_key    = cfg.get("app_key")
    app_secret = cfg.get("app_secret")

    raw_path = payload.clip_path.replace('\\', '/')
    candidates = [
        raw_path,
        os.path.join(OUTPUT_DIR, os.path.basename(raw_path)),
        os.path.abspath(raw_path),
    ]
    actual_file = next((c for c in candidates if c and os.path.exists(c) and os.path.isfile(c)), None)
    if not actual_file:
        raise HTTPException(status_code=404, detail=f"Video file not found at: {payload.clip_path}")

    try:
        result = TikTokService.upload_video(
            video_path=actual_file,
            title=payload.title,
            privacy_level=payload.privacy_level or "PUBLIC_TO_EVERYONE",
            token_data=token_row["token"],
            app_key=app_key,
            app_secret=app_secret,
        )
        record_social_post(
            job_id=payload.job_id or "",
            clip_path=payload.clip_path,
            platform="tiktok",
            post_id=result["publish_id"],
            post_url=result["share_url"],
            title=result["title"],
            caption=payload.caption or "",
            privacy=result["privacy"],
        )
        return result
    except Exception as e:
        print(f"[TikTok Publish Error] {e}")
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── Instagram Account Linking & Publishing Endpoints ────────────────────────

class InstagramConfigRequest(BaseModel):
    app_id:       str
    app_secret:   str
    redirect_uri: Optional[str] = None


class InstagramPublishRequest(BaseModel):
    clip_path:   str
    caption:     str
    title:       Optional[str] = ""
    privacy:     Optional[str] = "public"
    job_id:      Optional[str] = None
    public_url:  Optional[str] = None   # caller may supply the externally accessible URL


@app.get("/api/instagram/status")
def get_instagram_status():
    cfg        = get_instagram_config()
    token_info = get_instagram_token()
    app_id     = cfg.get("app_id", "").strip()
    app_secret = cfg.get("app_secret", "").strip()
    configured = bool(app_id and app_secret and len(app_id) > 3)
    return {
        "configured":   configured,
        "app_id":       app_id if configured else "",
        "redirect_uri": cfg.get("redirect_uri", "http://localhost:8000/api/instagram/callback"),
        "connected":    token_info is not None,
        "account": {
            "ig_user_id": token_info["ig_user_id"],
            "username":   token_info["username"],
            "name":       token_info["name"],
            "avatar":     token_info["avatar"],
        } if token_info else None,
    }


@app.post("/api/instagram/configure")
def configure_instagram(payload: InstagramConfigRequest):
    if not payload.app_id or not payload.app_secret:
        raise HTTPException(status_code=400, detail="app_id and app_secret are required")
    save_instagram_config(payload.app_id.strip(), payload.app_secret.strip(), payload.redirect_uri)
    return {"status": "saved", "message": "Instagram/Meta app credentials updated."}


@app.get("/api/instagram/auth-url")
def get_instagram_auth_url():
    cfg          = get_instagram_config()
    app_id       = cfg.get("app_id", "").strip()
    redirect_uri = cfg.get("redirect_uri", "http://localhost:8000/api/instagram/callback")
    if not app_id or len(app_id) < 3:
        raise HTTPException(
            status_code=400,
            detail="A valid Meta App ID is required. Please configure your App ID & Secret from developers.facebook.com."
        )
    auth_url = InstagramService.get_auth_url(app_id, redirect_uri)
    return {"auth_url": auth_url}


@app.get("/api/instagram/callback", response_class=HTMLResponse)
def instagram_oauth_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    if error:
        return HTMLResponse(f"""
        <!DOCTYPE html><html>
        <body style="font-family:sans-serif;background:#0f172a;color:#f87171;padding:40px;text-align:center;">
          <h2>Instagram Authorization Failed</h2><p>{error}</p>
          <button onclick="window.close()" style="background:#334155;color:#fff;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;">Close</button>
        </body></html>""")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code from Meta/Facebook")

    cfg          = get_instagram_config()
    app_id       = cfg.get("app_id")
    app_secret   = cfg.get("app_secret")
    redirect_uri = cfg.get("redirect_uri", "http://localhost:8000/api/instagram/callback")

    try:
        token_data   = InstagramService.exchange_code(code, app_id, app_secret, redirect_uri)
        profile_info = InstagramService.get_user_profile(token_data["access_token"])

        save_instagram_token(
            ig_user_id=profile_info["ig_user_id"],
            username=profile_info["username"],
            name=profile_info["name"],
            avatar=profile_info["avatar"],
            page_token=profile_info["page_token"],
            token_data=token_data,
        )

        account_json = json.dumps(profile_info)
        return HTMLResponse(f"""
        <!DOCTYPE html><html>
        <head><title>Instagram Connected</title></head>
        <body style="font-family:system-ui,sans-serif;background:#020617;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
          <div style="background:#0f172a;border:1px solid #334155;border-radius:24px;padding:32px;text-align:center;max-width:400px;box-shadow:0 0 40px rgba(0,0,0,0.5);">
            <div style="width:64px;height:64px;border-radius:50%;background:linear-gradient(135deg,#f09433,#e6683c,#dc2743,#cc2366,#bc1888);display:flex;align-items:center;justify-content:center;margin:0 auto 16px;font-size:28px;">&#128247;</div>
            <h2 style="margin:0 0 8px 0;color:#f8fafc;">Instagram Connected!</h2>
            <p style="color:#94a3b8;font-size:14px;margin:0 0 20px 0;"><b>@{profile_info['username']}</b> is now linked to Auto Shorts.</p>
            <p style="color:#64748b;font-size:12px;">This popup will close automatically...</p>
          </div>
          <script>
            try {{
              if (window.opener) {{
                window.opener.postMessage({{ type: 'INSTAGRAM_AUTH_SUCCESS', account: {account_json} }}, '*');
                setTimeout(() => window.close(), 1200);
              }} else {{
                setTimeout(() => window.location.href = '/', 1500);
              }}
            }} catch (e) {{ setTimeout(() => window.close(), 2000); }}
          </script>
        </body></html>""")
    except Exception as e:
        return HTMLResponse(f"""
        <!DOCTYPE html><html>
        <body style="font-family:sans-serif;background:#0f172a;color:#f87171;padding:40px;text-align:center;">
          <h2>Instagram Connection Error</h2><p>{str(e)}</p>
          <button onclick="window.close()" style="background:#334155;color:#fff;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;">Close</button>
        </body></html>""")


@app.post("/api/instagram/disconnect")
def disconnect_instagram():
    delete_instagram_token()
    return {"status": "disconnected", "message": "Instagram account unlinked."}


@app.post("/api/instagram/publish")
def publish_to_instagram(payload: InstagramPublishRequest):
    token_row = get_instagram_token()
    if not token_row:
        raise HTTPException(status_code=400, detail="No linked Instagram account. Please connect your Instagram account first.")

    cfg        = get_instagram_config()
    app_id     = cfg.get("app_id")
    app_secret = cfg.get("app_secret")

    # Instagram Graph API requires a PUBLIC URL — use the provided one or
    # fall back to constructing one from BACKEND_URL env var (if set).
    public_url = payload.public_url
    if not public_url:
        raw_path     = payload.clip_path.replace('\\', '/')
        basename     = os.path.basename(raw_path)
        backend_base = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
        public_url   = f"{backend_base}/output/{basename}"

    try:
        result = InstagramService.publish_reel(
            video_url=public_url,
            caption=payload.caption or "",
            token_data=token_row["token"],
            app_id=app_id,
            app_secret=app_secret,
            ig_user_id=token_row["ig_user_id"],
            page_token=token_row["page_token"],
        )
        record_social_post(
            job_id=payload.job_id or "",
            clip_path=payload.clip_path,
            platform="instagram",
            post_id=result["post_id"],
            post_url=result["permalink"],
            title=payload.title or "",
            caption=payload.caption or "",
            privacy=payload.privacy or "public",
        )
        return result
    except Exception as e:
        print(f"[Instagram Publish Error] {e}")
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/social/posts")
def get_all_social_posts(job_id: Optional[str] = None, platform: Optional[str] = None):
    """Unified history of all published posts across YouTube, TikTok, and Instagram."""
    return get_social_posts(job_id=job_id, platform=platform)

