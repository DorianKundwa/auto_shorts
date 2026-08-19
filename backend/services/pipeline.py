import os
import subprocess
from faster_whisper import WhisperModel
from services.llm_scorer import score_chunks
from services.video_processor import render_clip

def process_video(job_id: str, file_path: str, jobs_dict: dict):
    try:
        # Step 1: Extract Audio
        jobs_dict[job_id]["message"] = "Extracting audio..."
        jobs_dict[job_id]["progress"] = 10
        audio_path = f"uploads/{job_id}_audio.wav"
        
        # Using ffmpeg to extract audio
        subprocess.run([
            "ffmpeg", "-y", "-i", file_path, 
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", 
            audio_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Step 2: Transcription
        jobs_dict[job_id]["message"] = "Transcribing audio (CPU mode)..."
        jobs_dict[job_id]["progress"] = 30
        
        # Using tiny model for CPU speed. 
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
                
        # Step 3: LLM Scoring
        jobs_dict[job_id]["message"] = "Analyzing content for hooks..."
        jobs_dict[job_id]["progress"] = 60
        
        # We need a plain text transcript for the LLM
        full_text = " ".join([w["word"] for w in transcript_data])
        clips = score_chunks(full_text)
        
        # Step 4: Video generation
        jobs_dict[job_id]["message"] = f"Rendering {len(clips)} shorts..."
        jobs_dict[job_id]["progress"] = 80
        
        rendered_files = []
        for i, clip in enumerate(clips):
            # Find approximate start/end times in transcript_data based on text
            # For robustness, we fallback to random 15-second slices if text matching fails
            start_word = clip.get("start_text", "").split()[0] if clip.get("start_text") else ""
            
            # Simple heuristic for start time:
            start_time = 0.0
            for w in transcript_data:
                if w["word"].strip(".,!?").lower() == start_word.lower():
                    start_time = w["start"]
                    break
                    
            end_time = start_time + 15.0 # default to 15s if we can't find the end accurately
            
            # In a production app, we would use fuzzy matching on the entire substring to find exact start/end.
            
            out_file = f"output/{job_id}_short_{i}.mp4"
            render_clip(file_path, start_time, end_time, transcript_data, out_file)
            rendered_files.append(out_file)
            
        jobs_dict[job_id]["clips"] = rendered_files
        
        jobs_dict[job_id]["message"] = "Processing complete!"
        jobs_dict[job_id]["progress"] = 100
        jobs_dict[job_id]["status"] = "completed"
        
    except Exception as e:
        jobs_dict[job_id]["status"] = "failed"
        jobs_dict[job_id]["message"] = f"Error: {str(e)}"
        print(f"Error processing {job_id}: {e}")
