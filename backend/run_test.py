import os
import uuid
import sys

from database import init_db, create_job, get_job
from services.pipeline import process_video

def main():
    video_path = r"c:\Users\admin\Documents\auto_shorts\test\YTDown.com_YouTube_What-If-Every-Animal-Could-Talk_Media_842JVnH8qE0_001_1080p.mp4"
    
    if not os.path.exists(video_path):
        print(f"File not found: {video_path}")
        return

    init_db()
    job_id = str(uuid.uuid4())
    create_job(job_id, os.path.basename(video_path), "processing", 0, "Test job started")
    
    print(f"Starting pipeline for job {job_id} on {video_path}")
    process_video(job_id, video_path, os.path.basename(video_path), font="Montserrat-Black.ttf", destinations_str="TikTok, YouTube, Instagram")
    
    # Check final status
    final_job = get_job(job_id)
    print("\n--- FINAL JOB STATUS ---")
    print(final_job)

if __name__ == "__main__":
    main()
