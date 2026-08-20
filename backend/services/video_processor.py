import os
import cv2
import numpy as np
import subprocess
import tempfile
from moviepy import VideoFileClip, TextClip, CompositeVideoClip

# Resolve fonts directory relative to this file so it works regardless of CWD
_FONTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "fonts"))

# ─── Canvas sizes ────────────────────────────────────────────────────────────
# 720p output: significantly faster to encode than 1080p, still looks great on
# all mobile platforms. (~4× fewer pixels than 1080×1920)
_CANVAS_SIZES = {
    "tiktok":    (720, 1280),   # 9:16
    "youtube":   (720, 1280),   # 9:16
    "instagram": (720, 720),    # 1:1
}

def _get_canvas_size(destination: str):
    """Return (width, height) for the given destination platform."""
    key = destination.lower().replace(" ", "")
    for k, v in _CANVAS_SIZES.items():
        if k in key:
            return v
    return (720, 1280)  # safe default


def fit_to_aspect_ratio_blurred_bg(clip: VideoFileClip, destination: str):
    """
    Fits a standard video to the appropriate aspect ratio based on destination.
    Uses a blurred, scaled-up version of the video as the background.
    """
    bg_width, bg_height = _get_canvas_size(destination)

    clip_aspect = clip.w / clip.h
    target_aspect = bg_width / bg_height

    # Foreground: fit inside canvas
    if clip_aspect > target_aspect:
        fg_clip = clip.resized(width=bg_width)
    else:
        fg_clip = clip.resized(height=bg_height)

    # Background: fill canvas then crop to exact size
    if clip_aspect > target_aspect:
        bg_clip = clip.resized(height=bg_height)
        x_center = bg_clip.w / 2
        bg_clip = bg_clip.cropped(
            x1=x_center - bg_width / 2, y1=0,
            x2=x_center + bg_width / 2, y2=bg_height
        )
    else:
        bg_clip = clip.resized(width=bg_width)
        y_center = bg_clip.h / 2
        bg_clip = bg_clip.cropped(
            x1=0, y1=y_center - bg_height / 2,
            x2=bg_width, y2=y_center + bg_height / 2
        )

    # Speed-optimised blur: downsample to 1/8 scale, blur, upsample back
    scale = 8
    small_w, small_h = max(1, bg_width // scale), max(1, bg_height // scale)

    def blur_frame(image):
        small = cv2.resize(image, (small_w, small_h))
        blurred = cv2.GaussianBlur(small, (7, 7), 0)
        return cv2.resize(blurred, (bg_width, bg_height))

    bg = bg_clip.image_transform(blur_frame)
    return CompositeVideoClip([bg, fg_clip.with_position("center")])


def render_clip(
    video_path: str,
    start_time: float,
    end_time: float,
    transcript_words: list,
    output_path: str,
    font_name: str = "Montserrat-Black.ttf",
    destination: str = "TikTok",
):
    """
    Renders a single clip with captions, fitted to the destination aspect ratio.

    Speed strategy:
      1. MoviePy builds the composite (video + captions) and writes a raw pipe
         to ffmpeg's stdin.
      2. ffmpeg encodes with libx264 ultrafast + CRF 23 — far faster than
         MoviePy's built-in writer because ffmpeg can use native multithreading
         and optimised assembly for the encode step.
    """
    try:
        clip = VideoFileClip(video_path).subclipped(start_time, end_time)
        fitted_clip = fit_to_aspect_ratio_blurred_bg(clip, destination)

        bg_width, bg_height = _get_canvas_size(destination)

        # ── Caption words for this clip ───────────────────────────────────
        clip_words = [
            w for w in transcript_words
            if w["start"] >= start_time and w["end"] <= end_time
        ]

        # ── Font resolution ───────────────────────────────────────────────
        font_path = os.path.join(_FONTS_DIR, font_name)
        if not os.path.exists(font_path):
            print(f"[WARN] Font '{font_name}' not found at {font_path}, using Arial.")
            font_path = "Arial"

        # ── Build text clips (5 words per chunk) ─────────────────────────
        text_clips = []
        chunk_size = 5
        font_size = max(40, int(bg_width * 0.074))  # ~53px at 720w

        for i in range(0, len(clip_words), chunk_size):
            chunk = clip_words[i: i + chunk_size]
            if not chunk:
                continue

            chunk_text = " ".join([w["word"].upper() for w in chunk])
            rel_start = chunk[0]["start"] - start_time
            rel_end = chunk[-1]["end"] - start_time

            txt_clip = TextClip(
                text=chunk_text,
                font=font_path,
                font_size=font_size,
                color="white",
                stroke_color="black",
                stroke_width=3,
                method="caption",
                size=(int(bg_width * 0.85), None),
                text_align="center",
                margin=(15, 15),
            )
            txt_clip = (
                txt_clip
                .with_position(("center", int(fitted_clip.h * 0.75)))
                .with_start(rel_start)
                .with_end(rel_end)
            )
            text_clips.append(txt_clip)

        final_video = CompositeVideoClip([fitted_clip] + text_clips)

        # ── Fast encode via ffmpeg pipe ───────────────────────────────────
        _write_via_ffmpeg(final_video, output_path, fps=24)

        # Clean up
        final_video.close()
        fitted_clip.close()
        clip.close()

        return output_path

    except Exception as e:
        import traceback
        print(f"Error rendering clip: {e}")
        traceback.print_exc()
        return None



def _write_via_ffmpeg(clip, output_path: str, fps: int = 24):
    """
    Write a MoviePy composite clip to disk quickly.

    Strategy:
      Step 1 — pipe raw RGB frames into ffmpeg to produce a silent video fast.
      Step 2 — if audio exists, mux it in with a second ffmpeg call (copy stream,
               no re-encode needed for the video track).

    This avoids the MoviePy audio write deadlock: write_audiofile() blocks the
    Python process before ffmpeg starts receiving frames, causing a pipe hang.
    """
    w, h = int(clip.w), int(clip.h)
    silent_fd, silent_path = tempfile.mkstemp(suffix="_silent.mp4")
    os.close(silent_fd)

    try:
        # ── Step 1: encode video-only via stdin pipe ──────────────────────
        cmd_video = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{w}x{h}",
            "-pix_fmt", "rgb24",
            "-r", str(fps),
            "-i", "pipe:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-threads", "0",
            "-an",                # no audio in this pass
            silent_path,
        ]

        proc = subprocess.Popen(
            cmd_video,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        for frame in clip.iter_frames(fps=fps, dtype="uint8"):
            proc.stdin.write(frame.tobytes())

        proc.stdin.close()
        _, stderr = proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg video pass failed: {stderr.decode(errors='replace')}")

        # ── Step 2: mux audio from the composite clip ─────────────────────
        if clip.audio is not None:
            audio_fd, audio_path = tempfile.mkstemp(suffix=".wav")
            os.close(audio_fd)
            try:
                clip.audio.write_audiofile(
                    audio_path,
                    fps=44100,
                    codec="pcm_s16le",
                    logger=None,
                )
                cmd_mux = [
                    "ffmpeg", "-y",
                    "-i", silent_path,
                    "-i", audio_path,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-movflags", "+faststart",
                    "-shortest",
                    output_path,
                ]
                result = subprocess.run(
                    cmd_mux,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"ffmpeg mux failed: {result.stderr.decode(errors='replace')}"
                    )
            finally:
                if os.path.exists(audio_path):
                    os.remove(audio_path)
        else:
            # No audio — just rename the silent file to final output
            import shutil
            shutil.move(silent_path, output_path)
            silent_path = None  # prevent double-delete in finally

    finally:
        if silent_path and os.path.exists(silent_path):
            os.remove(silent_path)
