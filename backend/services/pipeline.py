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


def _find_phrase_start(words: list, phrase: str, search_after: float = 0.0):
    """
    Sliding-window phrase match.
    Returns the start timestamp of the first occurrence of 'phrase' whose
    first word begins at or after 'search_after' seconds.
    Falls back to single-token match if the full phrase is not found.
    """
    tokens = [_normalize(t) for t in phrase.split() if _normalize(t)]
    if not tokens:
        return None
    candidates = [w for w in words if w["start"] >= search_after]
    n = len(tokens)
    # Full phrase match (sliding window)
    for i in range(len(candidates) - n + 1):
        if [_normalize(candidates[j]["word"]) for j in range(i, i + n)] == tokens:
            return candidates[i]["start"]
    # Fallback: first-token match only
    for w in candidates:
        if _normalize(w["word"]) == tokens[0]:
            return w["start"]
    return None


def _find_phrase_end(words: list, phrase: str, search_after: float = 0.0):
    """
    Sliding-window phrase match.
    Returns the end timestamp of the first occurrence of 'phrase' whose
    first word begins at or after 'search_after' seconds.
    Falls back to last-token match if the full phrase is not found.
    """
    tokens = [_normalize(t) for t in phrase.split() if _normalize(t)]
    if not tokens:
        return None
    candidates = [w for w in words if w["start"] >= search_after]
    n = len(tokens)
    # Full phrase match (sliding window)
    for i in range(len(candidates) - n + 1):
        if [_normalize(candidates[j]["word"]) for j in range(i, i + n)] == tokens:
            return candidates[i + n - 1]["end"]
    # Fallback: last-token match only
    for w in candidates:
        if _normalize(w["word"]) == tokens[-1]:
            return w["end"]
    return None


def parse_transcript_file(file_path):
    if file_path.endswith('.json'):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
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


def process_video(job_id: str, file_path: str, original_filename: str, font: str = "Montserrat-Black.ttf", destinations_str: str = "TikTok", transcript_path: str = None, num_clips: int = 3):
    # Declare audio_path at function scope so the finally block can always reference it
    audio_path = f"uploads/{job_id}_audio.wav"
    try:
        destinations = [d.strip() for d in destinations_str.split(',')]

        # Step 0: Hash source video for cache key.
        # This lets us skip audio extraction entirely on cache hits.
        update_job(job_id, message="Checking cache...", progress=5)
        file_hash = hash_file(file_path)
        transcript_cache_path = os.path.join(CACHE_DIR, f"{file_hash}_transcript.json")
        hooks_cache_path = os.path.join(CACHE_DIR, f"{file_hash}_hooks.json")

        # Step 1: Transcription
        # Priority order: user-supplied transcript → cache → Whisper
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
                # Only extract audio when we actually need to transcribe
                update_job(job_id, message="Extracting audio...", progress=10)
                subprocess.run([
                    "ffmpeg", "-y", "-i", file_path,
                    "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    audio_path
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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

                with open(transcript_cache_path, 'w') as f:
                    json.dump(transcript_data, f)

        # Step 2: LLM Scoring
        if os.path.exists(hooks_cache_path):
            update_job(job_id, message="Loaded hooks from cache...", progress=70)
            with open(hooks_cache_path, 'r') as f:
                clips = json.load(f)
        else:
            update_job(job_id, message="Analyzing content for hooks...", progress=60)
            full_text = " ".join([w["word"] for w in transcript_data])
            # Pass word list so the fallback can use real timestamps
            clips = score_chunks(full_text, transcript_data, num_clips)

            with open(hooks_cache_path, 'w') as f:
                json.dump(clips, f)

        # Step 3: Video generation
        total_renders = len(clips) * len(destinations)
        render_index  = 0
        update_job(job_id, message=f"Rendering {len(clips)} short(s) for {len(destinations)} platform(s)...", progress=80)

        base_name = os.path.splitext(original_filename)[0]
        base_name = "".join([c for c in base_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
        job_output_dir = f"output/{base_name}"
        os.makedirs(job_output_dir, exist_ok=True)

        rendered_files = []
        for i, clip in enumerate(clips):
            start_text = clip.get("start_text", "")
            end_text   = clip.get("end_text",   "")
            title      = clip.get("title",      f"short_{i}")

            start_time = _find_phrase_start(transcript_data, start_text)
            if start_time is None:
                start_time = 0.0

            end_time = _find_phrase_end(transcript_data, end_text, search_after=start_time)
            if end_time is None or end_time <= start_time:
                end_time = start_time + 60.0

            if end_time - start_time > 65.0:
                end_time = start_time + 60.0

            safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
            if not safe_title:
                safe_title = f"short_{i}"

            for dest in destinations:
                dest_clean = dest.lower().replace(" ", "")
                out_file   = f"{job_output_dir}/{safe_title}_{dest_clean}.mp4"

                result = render_clip(file_path, start_time, end_time, transcript_data, out_file, font, dest)

                render_index += 1
                progress = 80 + int(render_index / total_renders * 18)  # 80 → 98
                update_job(
                    job_id,
                    progress=progress,
                    message=f"Rendered {render_index}/{total_renders}: {title[:40]}..."
                    if len(title) > 40 else f"Rendered {render_index}/{total_renders}: {title}",
                )

                if result:
                    # Store path + title so the UI can display LLM-generated names
                    rendered_files.append({
                        "path":  result.replace(os.sep, '/'),
                        "title": title,
                    })

        update_job(job_id, message="Processing complete!", progress=100, status="completed", clips=rendered_files)

    except Exception as e:
        update_job(job_id, status="failed", message=f"Error: {str(e)}")
        print(f"Error processing {job_id}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Fix #13: always clean up temporary upload files regardless of success/failure
        for path in [file_path, audio_path, transcript_path]:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
