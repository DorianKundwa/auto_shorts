import os
import subprocess
import hashlib
import json
from faster_whisper import WhisperModel
from services.llm_scorer import score_chunks
from services.video_processor import render_clip
from database import update_job

CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def hash_file(file_path):
    """Generate MD5 hash of a file to use as a cache key."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as afile:
        buf = afile.read()
        hasher.update(buf)
    return hasher.hexdigest()

def process_video(job_id: str, file_path: str):
    try:
        # Step 1: Extract Audio
        update_job(job_id, message="Extracting audio...", progress=10)
        audio_path = f"uploads/{job_id}_audio.wav"
        
        # Using ffmpeg to extract audio
        subprocess.run([
            "ffmpeg", "-y", "-i", file_path, 
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", 
            audio_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Calculate file hash for caching based on audio
        file_hash = hash_file(audio_path)
        transcript_cache_path = os.path.join(CACHE_DIR, f"{file_hash}_transcript.json")
        hooks_cache_path = os.path.join(CACHE_DIR, f"{file_hash}_hooks.json")
        
        # Step 2: Transcription
        if os.path.exists(transcript_cache_path):
            update_job(job_id, message="Loaded transcription from cache...", progress=40)
            with open(transcript_cache_path, 'r') as f:
                transcript_data = json.load(f)
        else:
            update_job(job_id, message="Transcribing audio (CPU mode)...", progress=30)
            model_size = "tiny"
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            
            segments, info = model.transcribe(audio_path, word_timestamps=True)
            
            transcript_data = []
            for segment in segments:
                for word in segment.words:
                    transcript_data.append({
                        "word": word.word,
                        "start": word.start,
                        "end": word.end
                    })
            
            # Save to cache
            with open(transcript_cache_path, 'w') as f:
                json.dump(transcript_data, f)
                
        # Step 3: LLM Scoring
        if os.path.exists(hooks_cache_path):
            update_job(job_id, message="Loaded hooks from cache...", progress=70)
            with open(hooks_cache_path, 'r') as f:
                clips = json.load(f)
        else:
            update_job(job_id, message="Analyzing content for hooks...", progress=60)
            full_text = " ".join([w["word"] for w in transcript_data])
            clips = score_chunks(full_text)
            
            with open(hooks_cache_path, 'w') as f:
                json.dump(clips, f)
        
        # Step 4: Video generation
        update_job(job_id, message=f"Rendering {len(clips)} shorts...", progress=80)
        
        # Create output directory for this job
        job_output_dir = f"output/{job_id}"
        os.makedirs(job_output_dir, exist_ok=True)
        
        rendered_files = []
        for i, clip in enumerate(clips):
            start_word = clip.get("start_text", "").split()[0] if clip.get("start_text") else ""
            
            start_time = 0.0
            for w in transcript_data:
                if w["word"].strip(".,!?").lower() == start_word.lower():
                    start_time = w["start"]
                    break
                    
            end_time = start_time + 15.0 # default 15s
            
            out_file = f"{job_output_dir}/short_{i}.mp4"
            render_clip(file_path, start_time, end_time, transcript_data, out_file)
            rendered_files.append(out_file)
            
        update_job(job_id, message="Processing complete!", progress=100, status="completed", clips=rendered_files)
        
    except Exception as e:
        update_job(job_id, status="failed", message=f"Error: {str(e)}")
        print(f"Error processing {job_id}: {e}")
