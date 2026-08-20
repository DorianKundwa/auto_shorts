import os
import subprocess
import hashlib
import json
import re
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

def _normalize(word: str) -> str:
    """Strip all non-alphanumeric characters and lowercase for robust matching."""
    return re.sub(r'[^a-z0-9]', '', word.lower())

def parse_transcript_file(file_path):
    if file_path.endswith('.json'):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # If it's whisper JSON, it usually has a 'segments' or 'words' key
            if isinstance(data, dict) and 'words' in data:
                return data['words']
            elif isinstance(data, dict) and 'segments' in data:
                words = []
                for s in data['segments']:
                    if 'words' in s:
                        words.extend(s['words'])
                return words
            elif isinstance(data, list):
                return data
            return data
    elif file_path.endswith('.srt'):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        blocks = content.strip().split('\n\n')
        transcript_data = []
        for block in blocks:
            lines = block.split('\n')
            if len(lines) >= 3:
                time_line = lines[1]
                text = " ".join(lines[2:])
                m = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})', time_line)
                if m:
                    h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, m.groups())
                    start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0
                    end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0
                    words = text.split()
                    if words:
                        duration_per_word = (end - start) / len(words)
                        for i, word in enumerate(words):
                            transcript_data.append({
                                "word": word,
                                "start": start + i * duration_per_word,
                                "end": start + (i + 1) * duration_per_word
                            })
        return transcript_data
    return None

def process_video(job_id: str, file_path: str, original_filename: str, font: str = "Montserrat-Black.ttf", destinations_str: str = "TikTok", transcript_path: str = None):
    try:
        destinations = [d.strip() for d in destinations_str.split(',')]

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
        # Bug #5 fix: user-provided transcript has its own dedicated code path.
        # Only fall through to cache/Whisper if no transcript was provided at all.
        transcript_data = None

        if transcript_path and os.path.exists(transcript_path):
            update_job(job_id, message="Loading user-provided transcript...", progress=40)
            transcript_data = parse_transcript_file(transcript_path)
            if not transcript_data:
                update_job(job_id, message="User transcript parse failed, falling back to Whisper...", progress=25)

        if not transcript_data:
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

        # Create output directory based on original filename
        base_name = os.path.splitext(original_filename)[0]
        # Clean basename for safety
        base_name = "".join([c for c in base_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
        job_output_dir = f"output/{base_name}"
        os.makedirs(job_output_dir, exist_ok=True)

        rendered_files = []
        for i, clip in enumerate(clips):
            # Bug #3 fix: use _normalize() for robust word matching that handles
            # punctuation, apostrophes, colons, quotes, etc.
            start_words = clip.get("start_text", "").split()
            end_words = clip.get("end_text", "").split()

            start_token = _normalize(start_words[0]) if start_words else ""
            end_token = _normalize(end_words[-1]) if end_words else ""

            start_time = 0.0
            end_time = 0.0

            for w in transcript_data:
                norm_word = _normalize(w["word"])
                if norm_word == start_token and start_time == 0.0 and start_token:
                    start_time = w["start"]
                if norm_word == end_token and start_time > 0.0 and end_token:
                    end_time = w["end"]

            if end_time <= start_time:
                end_time = start_time + 60.0  # fallback to 60s

            # Cap at 60s max
            if end_time - start_time > 65.0:
                end_time = start_time + 60.0

            raw_title = clip.get("title", f"short_{i}")
            safe_title = "".join([c for c in raw_title if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
            if not safe_title:
                safe_title = f"short_{i}"

            for dest in destinations:
                dest_clean = dest.lower().replace(" ", "")
                out_file = f"{job_output_dir}/{safe_title}_{dest_clean}.mp4"

                # Render using the selected font and destination aspect ratio
                result = render_clip(file_path, start_time, end_time, transcript_data, out_file, font, dest)
                if result:
                    # Bug #6 fix: normalize path separators to forward slashes so
                    # the browser can construct a valid URL from the stored path.
                    rendered_files.append(result.replace(os.sep, '/'))

        update_job(job_id, message="Processing complete!", progress=100, status="completed", clips=rendered_files)

    except Exception as e:
        update_job(job_id, status="failed", message=f"Error: {str(e)}")
        print(f"Error processing {job_id}: {e}")
        import traceback
        traceback.print_exc()
