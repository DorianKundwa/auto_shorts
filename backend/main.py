from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import uuid
import shutil
from services.pipeline import process_video
from database import init_db, create_job, get_job, get_all_jobs

app = FastAPI(title="Auto Shorts API")

# Allow CORS for local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow any local port
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Serve output directory for the frontend to preview videos
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")

# Initialize SQLite DB
init_db()

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Auto Shorts API running"}

@app.post("/api/upload")
async def upload_video(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...),
    transcript: UploadFile = File(None),
    font: str = Form("Montserrat-Black.ttf"),
    destinations: str = Form("TikTok"),
    num_clips: int = Form(3),
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
            
    num_clips = max(1, min(num_clips, 5))  # clamp to 1–5
    create_job(job_id, file.filename, "processing", 0, "Video uploaded, starting processing")
    background_tasks.add_task(process_video, job_id, file_path, file.filename, font, destinations, transcript_path, num_clips)
    
    return {"job_id": job_id, "message": "Upload successful, processing started."}

@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/api/jobs")
def list_jobs():
    return get_all_jobs()
