import os
import cv2
import numpy as np
import subprocess
import tempfile
from moviepy import VideoFileClip, TextClip, CompositeVideoClip, ColorClip

# Resolve paths relative to this file so the module works from any CWD
_FONTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "fonts"))
_HAAR_PATH  = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "haarcascade_frontalface_default.xml"))

# Lazy-loaded face cascade (avoids startup cost when face detection isn't needed)
_face_cascade = None

# ─── Canvas sizes ─────────────────────────────────────────────────────────────
_CANVAS_SIZES = {
    "tiktok":    (720, 1280),   # 9:16
    "youtube":   (720, 1280),   # 9:16  (YouTube Shorts)
    "instagram": (720, 720),    # 1:1
}


def _get_canvas_size(destination: str):
    """Return (width, height) for the given destination platform."""
    key = destination.lower().replace(" ", "")
    for k, v in _CANVAS_SIZES.items():
        if k in key:
            return v
    return (720, 1280)


def _get_face_cascade():
    """Lazily load the OpenCV Haar face cascade once per process."""
    global _face_cascade
    if _face_cascade is None and os.path.exists(_HAAR_PATH):
        _face_cascade = cv2.CascadeClassifier(_HAAR_PATH)
    return _face_cascade


def _detect_face_x(clip: VideoFileClip):
    """
    Sample the middle frame of a clip and locate the largest face.
    Returns the face-centre as a normalised X coordinate (0.0–1.0),
    or None when no face is found or the cascade is unavailable.
    """
    try:
        cascade = _get_face_cascade()
        if cascade is None or cascade.empty():
            return None
        t = min(clip.duration / 2, clip.duration - 0.05)
        frame = clip.get_frame(t)
        gray  = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        faces = cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40)
        )
        if len(faces) == 0:
            return None
        # Pick the largest face (most prominent speaker)
        x, _, w, _ = max(faces, key=lambda f: f[2] * f[3])
        return (x + w / 2) / frame.shape[1]   # normalised 0–1
    except Exception:
        return None


def fit_to_aspect_ratio_blurred_bg(clip: VideoFileClip, destination: str, face_x: float = None):
    """
    Fit the source clip to the target canvas with a blurred background fill.

    face_x (optional) — normalised horizontal face position (0.0–1.0).
    When supplied, the background crop is shifted to keep the face centred
    rather than always defaulting to the frame midpoint.
    """
    bg_width, bg_height = _get_canvas_size(destination)
    clip_aspect   = clip.w / clip.h
    target_aspect = bg_width / bg_height

    # ── Foreground: letterbox / pillarbox inside canvas ──────────────────
    if clip_aspect > target_aspect:
        fg_clip = clip.resized(width=bg_width)
    else:
        fg_clip = clip.resized(height=bg_height)

    # ── Background: zoom-fill then crop to exact canvas size ─────────────
    if clip_aspect > target_aspect:
        bg_clip = clip.resized(height=bg_height)
        if face_x is not None:
            # Slide the crop window so the face ends up centred
            face_px = face_x * bg_clip.w
            x1 = max(0.0, min(face_px - bg_width / 2, bg_clip.w - bg_width))
        else:
            x1 = (bg_clip.w - bg_width) / 2
        bg_clip = bg_clip.cropped(x1=x1, y1=0, x2=x1 + bg_width, y2=bg_height)
    else:
        bg_clip = clip.resized(width=bg_width)
        y1 = (bg_clip.h - bg_height) / 2
        bg_clip = bg_clip.cropped(x1=0, y1=y1, x2=bg_width, y2=y1 + bg_height)

    # ── Improved blur: 1/8-scale downsample + Gaussian ───────────────────
    # Previously used 1/16 + box blur which produced a blocky look.
    # INTER_AREA downsampling + Gaussian at 1/8 scale is still fast but
    # produces a smooth, cinematic bokeh effect.
    small_w = max(1, bg_width  // 8)
    small_h = max(1, bg_height // 8)

    def blur_frame(image):
        small   = cv2.resize(image,   (small_w, small_h), interpolation=cv2.INTER_AREA)
        blurred = cv2.GaussianBlur(small, (7, 7), 0)
        return  cv2.resize(blurred, (bg_width, bg_height), interpolation=cv2.INTER_LINEAR)

    bg = bg_clip.image_transform(blur_frame)
    return CompositeVideoClip([bg, fg_clip.with_position("center")])


def render_clip(
    video_path:       str,
    start_time:       float,
    end_time:         float,
    transcript_words: list,
    output_path:      str,
    font_name:        str   = "Montserrat-Black.ttf",
    destination:      str   = "TikTok",
):
    """
    Render a single short with:
      • Face-detection-aware blurred background crop
      • Word-by-word karaoke captions (each word timed to its spoken duration)
        with a semi-transparent pill background for contrast on any scene
    """
    clip        = None
    fitted_clip = None
    final_video = None
    try:
        clip = VideoFileClip(video_path).subclipped(start_time, end_time)

        # Detect speaker face for smarter background crop
        face_x = _detect_face_x(clip)
        if face_x is not None:
            print(f"[VIDEO] Face detected at x={face_x:.2f} — centering background crop")

        fitted_clip = fit_to_aspect_ratio_blurred_bg(clip, destination, face_x)
        bg_width, bg_height = _get_canvas_size(destination)

        # ── Words that fall inside this clip ─────────────────────────────
        clip_words = [
            w for w in transcript_words
            if w["start"] >= start_time and w["start"] < end_time
        ]

        # ── Font ──────────────────────────────────────────────────────────
        font_path = os.path.join(_FONTS_DIR, font_name)
        if not os.path.exists(font_path):
            print(f"[WARN] Font '{font_name}' not found — falling back to Arial.")
            font_path = "Arial"

        # ── Karaoke (word-by-word) captions ──────────────────────────────
        # Every word gets its own TextClip timed to its Whisper timestamp.
        # A fixed-size semi-transparent pill sits behind each word for
        # readability on any background.  This matches the dominant caption
        # style used by viral TikTok / Shorts content.
        text_clips = []
        font_size  = max(48, int(bg_width * 0.088))   # ~63 px at 720 w
        caption_cy = int(fitted_clip.h * 0.76)        # vertical centre of caption band
        pill_h     = font_size + 32
        pill_w     = int(bg_width * 0.88)
        pill_top   = caption_cy - pill_h // 2         # top-Y for position()

        for w in clip_words:
            word_text = w["word"].strip().upper()
            if not word_text:
                continue
            rel_start = max(0.0, w["start"] - start_time)
            rel_end   = min(fitted_clip.duration, w["end"] - start_time)
            if rel_end - rel_start < 0.04:            # skip whisper artefacts < 40 ms
                continue

            # Dark semi-transparent pill background
            pill = (
                ColorClip(size=(pill_w, pill_h), color=(10, 10, 10))
                .with_opacity(0.58)
                .with_position(("center", pill_top))
                .with_start(rel_start)
                .with_end(rel_end)
            )

            # Word text — centred vertically on the pill
            txt = TextClip(
                text=word_text,
                font=font_path,
                font_size=font_size,
                color="white",
                stroke_color="black",
                stroke_width=3,
                method="caption",
                size=(int(bg_width * 0.80), None),
                text_align="center",
            )
            txt_top = caption_cy - txt.h // 2
            txt = (
                txt
                .with_position(("center", txt_top))
                .with_start(rel_start)
                .with_end(rel_end)
            )

            text_clips.extend([pill, txt])

        final_video = CompositeVideoClip([fitted_clip] + text_clips)

        # ── Encode + mux ─────────────────────────────────────────────────
        _write_via_ffmpeg(
            clip=final_video,
            output_path=output_path,
            source_video_path=video_path,
            start_time=start_time,
            end_time=end_time,
            fps=24,
        )

        return output_path

    except Exception as e:
        import traceback
        print(f"Error rendering clip: {e}")
        traceback.print_exc()
        return None
    finally:
        for obj in [final_video, fitted_clip, clip]:
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass


def _write_via_ffmpeg(
    clip,
    output_path:       str,
    source_video_path: str,
    start_time:        float,
    end_time:          float,
    fps:               int = 24,
):
    """
    Two-pass ffmpeg write:
      Pass 1 — stream raw RGB frames through stdin → silent H.264 file.
      Pass 2 — mux audio from the source video (-ss / -t), bypassing
               Python audio rendering entirely (fast + lossless seek).
    """
    w, h = int(clip.w), int(clip.h)
    silent_fd, silent_path = tempfile.mkstemp(suffix="_silent.mp4")
    os.close(silent_fd)

    try:
        # ── Pass 1: video-only ────────────────────────────────────────────
        cmd_video = [
            "ffmpeg", "-y",
            "-loglevel", "error",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{w}x{h}",
            "-pix_fmt", "rgb24",
            "-r", str(fps),
            "-i", "pipe:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-threads", "0",
            "-an",
            silent_path,
        ]
        proc = subprocess.Popen(
            cmd_video, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for frame in clip.iter_frames(fps=fps, dtype="uint8"):
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg video pass exited with code {proc.returncode}")

        # ── Pass 2: mux audio ─────────────────────────────────────────────
        cmd_mux = [
            "ffmpeg", "-y",
            "-i", silent_path,
            "-ss", str(start_time),
            "-t",  str(end_time - start_time),   # duration, not absolute -to
            "-i", source_video_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k",
            "-map", "0:v:0",
            "-map", "1:a:0?",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg mux failed: {result.stderr.decode(errors='replace')}"
            )
    finally:
        if silent_path and os.path.exists(silent_path):
            try:
                os.remove(silent_path)
            except Exception:
                pass
