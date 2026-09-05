import os
import subprocess
import hashlib
import json
import re
from typing import List, Dict, Any, Optional
from faster_whisper import WhisperModel
from services.llm_scorer import score_chunks
from services.audio_analyzer import analyze_audio_energy, get_segment_energy_score
from services.video_processor import render_clip
from database import update_job, get_job

CACHE_DIR = "cache"
PREVIEWS_DIR = "output/previews"
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(PREVIEWS_DIR, exist_ok=True)


def hash_file(file_path: str) -> str:
    """Generate MD5 hash of a file to use as a cache key."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as afile:
        buf = afile.read()
        hasher.update(buf)
    return hasher.hexdigest()


def _normalize(word: str) -> str:
    """Strip non-alphanumeric characters and lowercase for robust matching."""
    return re.sub(r'[^a-z0-9]', '', word.lower())


def _find_phrase_start(words: list, phrase: str, search_after: float = 0.0) -> Optional[float]:
    """Sliding-window phrase match for start timestamp."""
    tokens = [_normalize(t) for t in phrase.split() if _normalize(t)]
    if not tokens:
        return None
    candidates = [w for w in words if w["start"] >= search_after]
    n = len(tokens)
    for i in range(len(candidates) - n + 1):
        if [_normalize(candidates[j]["word"]) for j in range(i, i + n)] == tokens:
            return candidates[i]["start"]
    for w in candidates:
        if _normalize(w["word"]) == tokens[0]:
            return w["start"]
    return None


def _find_phrase_end(words: list, phrase: str, search_after: float = 0.0) -> Optional[float]:
    """Sliding-window phrase match for end timestamp."""
    tokens = [_normalize(t) for t in phrase.split() if _normalize(t)]
    if not tokens:
        return None
    candidates = [w for w in words if w["start"] >= search_after]
    n = len(tokens)
    for i in range(len(candidates) - n + 1):
        if [_normalize(candidates[j]["word"]) for j in range(i, i + n)] == tokens:
            return candidates[i + n - 1]["end"]
    for w in candidates:
        if _normalize(w["word"]) == tokens[-1]:
            return w["end"]
    return None


def parse_transcript_file(file_path: str):
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


def generate_fast_preview(source_video: str, start_time: float, end_time: float, output_path: str) -> Optional[str]:
    """Generate a lightweight 360p preview MP4 in ~1-2 seconds using FFmpeg ultrafast preset."""
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        duration = max(1.0, end_time - start_time)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(max(0.0, start_time)),
            "-i", source_video,
            "-t", str(duration),
            "-vf", "scale=-2:360",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-c:a", "aac",
            "-b:a", "96k",
            output_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(output_path):
            return output_path.replace(os.sep, '/')
    except Exception as e:
        print(f"[Pipeline] Fast preview generation failed: {e}")
    return None


def analyze_video_stage(
    job_id: str,
    file_path: str,
    original_filename: str,
    font: str = "Montserrat-Black.ttf",
    destinations_str: str = "TikTok",
    transcript_path: Optional[str] = None,
    num_clips: int = 3,
    custom_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stage 1: Multi-Modal Analysis & Fast Preview Generation.
    - Extracts audio and computes RMS energy profile.
    - Transcribes with Whisper.
    - Scores viral hooks with LLM Chain-of-Thought (30s–90s dynamic lengths).
    - Generates lightweight 360p previews for in-browser review.
    """
    audio_path = f"uploads/{job_id}_audio.wav"
    file_hash = hash_file(file_path)
    transcript_cache_path = os.path.join(CACHE_DIR, f"{file_hash}_transcript.json")
    audio_analysis_cache = os.path.join(CACHE_DIR, f"{file_hash}_audio_analysis.json")
    hooks_cache_path = os.path.join(CACHE_DIR, f"{file_hash}_hooks_v2.json")

    # Step 1: Audio Extraction & Multi-Modal Energy Analysis
    update_job(job_id, message="Extracting audio and analyzing vocal energy...", progress=15)
    if not os.path.exists(audio_path):
        subprocess.run([
            "ffmpeg", "-y", "-i", file_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            audio_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if os.path.exists(audio_analysis_cache):
        with open(audio_analysis_cache, 'r') as f:
            audio_analysis = json.load(f)
    else:
        audio_analysis = analyze_audio_energy(audio_path)
        with open(audio_analysis_cache, 'w') as f:
            json.dump(audio_analysis, f)

    # Step 2: Transcription
    transcript_data = None
    if transcript_path and os.path.exists(transcript_path):
        update_job(job_id, message="Loading user-provided transcript...", progress=35)
        transcript_data = parse_transcript_file(transcript_path)

    if not transcript_data:
        if os.path.exists(transcript_cache_path):
            update_job(job_id, message="Loaded transcript from cache...", progress=40)
            with open(transcript_cache_path, 'r') as f:
                transcript_data = json.load(f)
        else:
            update_job(job_id, message="Transcribing speech with AI (Whisper)...", progress=35)
            model = WhisperModel("tiny", device="cpu", compute_type="int8")
            segments, _ = model.transcribe(audio_path, word_timestamps=True)
            transcript_data = [
                {"word": word.word, "start": word.start, "end": word.end}
                for segment in segments
                for word in segment.words
            ]
            with open(transcript_cache_path, 'w') as f:
                json.dump(transcript_data, f)

    video_duration = audio_analysis.get("duration", 0.0)
    if video_duration <= 0 and transcript_data:
        video_duration = transcript_data[-1]["end"]

    # Step 3: Multi-modal Hook Detection with LLM (CoT + Energy + Dynamic Lengths 30s-90s)
    update_job(job_id, message="Detecting viral hooks with Chain-of-Thought AI...", progress=55)
    full_text = " ".join([w["word"] for w in transcript_data])
    raw_clips = score_chunks(
        transcript_text=full_text,
        transcript_words=transcript_data,
        num_clips=num_clips,
        audio_analysis=audio_analysis,
        min_duration=30,
        max_duration=90,
        custom_prompt=custom_prompt,
    )

    # Step 4: Map timestamps & generate fast 360p previews
    update_job(job_id, message="Generating instant in-browser segment previews...", progress=65)
    base_name = os.path.splitext(original_filename)[0]
    base_name = "".join([c for c in base_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
    job_preview_dir = f"output/{base_name}/previews"
    os.makedirs(job_preview_dir, exist_ok=True)

    candidates = []
    for i, clip in enumerate(raw_clips):
        title = clip.get("title", f"Hook {i + 1}")
        hook_category = clip.get("hook_category", "Curiosity Gap")
        reason = clip.get("reason", "High viral potential.")
        virality_tip = clip.get("virality_tip", "Start right away on the punchline.")
        engagement_score = float(clip.get("engagement_score", 8.5))
        retention_score = float(clip.get("retention_score", engagement_score))
        emotion_score = float(clip.get("emotion_score", 8.0))
        highlight_words = clip.get("highlight_words", [])
        social_kit = clip.get("social_kit", None)
        start_text = clip.get("start_text", "")
        end_text = clip.get("end_text", "")

        # Find start and end timestamps
        start_time = _find_phrase_start(transcript_data, start_text)
        if start_time is None:
            start_time = float(i * 45)

        end_time = _find_phrase_end(transcript_data, end_text, search_after=start_time)
        if end_time is None or end_time <= start_time:
            end_time = start_time + 45.0

        # Dynamic bounds check (allow 25s to 95s)
        clip_dur = end_time - start_time
        if clip_dur < 25.0:
            end_time = min(video_duration, start_time + 35.0)
        elif clip_dur > 95.0:
            end_time = start_time + 85.0

        start_time = round(max(0.0, float(start_time)), 2)
        end_time = round(min(video_duration if video_duration > 0 else end_time, float(end_time)), 2)
        duration = round(end_time - start_time, 2)

        # Calculate multi-modal audio energy score (0-100)
        energy_score = int(get_segment_energy_score(start_time, end_time, audio_analysis) * 100)

        # Generate fast preview
        preview_file = f"{job_preview_dir}/preview_clip_{i + 1}.mp4"
        preview_url = generate_fast_preview(file_path, start_time, end_time, preview_file)

        candidates.append({
            "id": f"clip_{i + 1}",
            "title": title,
            "hook_category": hook_category,
            "reason": reason,
            "virality_tip": virality_tip,
            "engagement_score": round(engagement_score, 1),
            "retention_score": round(retention_score, 1),
            "emotion_score": round(emotion_score, 1),
            "energy_score": energy_score,
            "highlight_words": highlight_words,
            "social_kit": social_kit,
            "start_time": start_time,
            "end_time": end_time,
            "duration": duration,
            "preview_url": preview_url,
            "selected": True,
        })

    metadata = {
        "candidates": candidates,
        "audio_timeline": audio_analysis.get("timeline", []),
        "audio_peaks": audio_analysis.get("peaks", []),
        "video_duration": round(video_duration, 2),
        "source_file": file_path,
        "original_filename": original_filename,
        "font": font,
        "destinations": destinations_str,
        "transcript_cache": transcript_cache_path,
    }

    update_job(
        job_id,
        status="review_ready",
        progress=70,
        message="Hooks detected! Preview and fine-tune your clips.",
        metadata=metadata,
    )

    return metadata


def render_custom_clips(
    job_id: str,
    clips_to_render: List[Dict[str, Any]],
    font: str = "Montserrat-Black.ttf",
    destinations_str: str = "TikTok",
) -> List[Dict[str, Any]]:
    """
    Stage 2: Final Multi-Platform Video Rendering.
    Takes user-customized trimmed segments and renders face-tracked,
    blurred-background, karaoke-captioned videos for all chosen platforms.
    """
    job = get_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    metadata = job.get("metadata", {})
    file_path = metadata.get("source_file") or f"uploads/{job_id}_{job['filename']}"
    original_filename = metadata.get("original_filename") or job["filename"]
    transcript_cache = metadata.get("transcript_cache")

    transcript_data = []
    if transcript_cache and os.path.exists(transcript_cache):
        with open(transcript_cache, 'r') as f:
            transcript_data = json.load(f)

    destinations = [d.strip() for d in destinations_str.split(',') if d.strip()]
    if not destinations:
        destinations = ["TikTok"]

    selected_clips = [c for c in clips_to_render if c.get("selected", True)]
    if not selected_clips:
        update_job(job_id, status="completed", progress=100, message="No clips were selected for rendering.", clips=[])
        return []

    total_renders = len(selected_clips) * len(destinations)
    render_index = 0

    base_name = os.path.splitext(original_filename)[0]
    base_name = "".join([c for c in base_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
    job_output_dir = f"output/{base_name}"
    os.makedirs(job_output_dir, exist_ok=True)

    rendered_files = []
    update_job(job_id, status="rendering", progress=75, message=f"Rendering {len(selected_clips)} short(s) for {len(destinations)} platform(s)...")

    for i, clip in enumerate(selected_clips):
        title = clip.get("title") or f"short_{i + 1}"
        start_time = float(clip.get("start_time", 0.0))
        end_time = float(clip.get("end_time", start_time + 45.0))
        highlight_words = clip.get("highlight_words", [])

        safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
        if not safe_title:
            safe_title = f"short_{i + 1}"

        for dest in destinations:
            dest_clean = dest.lower().replace(" ", "")
            out_file = f"{job_output_dir}/{safe_title}_{dest_clean}.mp4"

            result = render_clip(
                file_path,
                start_time,
                end_time,
                transcript_data,
                out_file,
                font,
                dest,
                highlight_words=highlight_words,
            )
            render_index += 1
            progress = 75 + int(render_index / total_renders * 24)  # 75 -> 99
            update_job(
                job_id,
                progress=progress,
                message=f"Rendered {render_index}/{total_renders}: {title[:35]}..." if len(title) > 35 else f"Rendered {render_index}/{total_renders}: {title}"
            )

            if result:
                rendered_files.append({
                    "path": result.replace(os.sep, '/'),
                    "title": title,
                    "destination": dest,
                    "duration": round(end_time - start_time, 1),
                })

    update_job(job_id, status="completed", progress=100, message="Processing complete! Your shorts are ready.", clips=rendered_files)
    return rendered_files


def process_video(
    job_id: str,
    file_path: str,
    original_filename: str,
    font: str = "Montserrat-Black.ttf",
    destinations_str: str = "TikTok",
    transcript_path: Optional[str] = None,
    num_clips: int = 3,
    auto_render: bool = False,
    custom_prompt: Optional[str] = None,
):
    """
    Main pipeline entry point. Runs multi-modal analysis, and if auto_render is True,
    continues directly to rendering. Otherwise leaves job in 'review_ready' state for UI trimming.
    """
    audio_path = f"uploads/{job_id}_audio.wav"
    try:
        metadata = analyze_video_stage(
            job_id=job_id,
            file_path=file_path,
            original_filename=original_filename,
            font=font,
            destinations_str=destinations_str,
            transcript_path=transcript_path,
            num_clips=num_clips,
            custom_prompt=custom_prompt,
        )

        if auto_render:
            candidates = metadata.get("candidates", [])
            render_custom_clips(job_id, candidates, font, destinations_str)

    except Exception as e:
        update_job(job_id, status="failed", message=f"Error: {str(e)}")
        print(f"Error processing {job_id}: {e}")
        import traceback
        traceback.print_exc()
