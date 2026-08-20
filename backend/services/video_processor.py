import os
import cv2
import numpy as np
from moviepy import VideoFileClip, TextClip, CompositeVideoClip, ColorClip

def fit_to_aspect_ratio_blurred_bg(clip: VideoFileClip, destination: str):
    """
    Fits a standard video to the appropriate aspect ratio based on destination.
    Uses a blurred, scaled-up version of the video as the background.
    TikTok: 1080x1920 (9:16)
    YouTube: 1920x1080 (16:9)
    Instagram: 1080x1080 (1:1)
    """
    dest = destination.lower()
    if 'youtube' in dest:
        bg_width, bg_height = 1920, 1080
    elif 'instagram' in dest:
        bg_width, bg_height = 1080, 1080
    else: # default to TikTok 9:16
        bg_width, bg_height = 1080, 1920
        
    clip_aspect = clip.w / clip.h
    target_aspect = bg_width / bg_height
    
    # Create the foreground clip
    if clip_aspect > target_aspect:
        fg_clip = clip.resized(width=bg_width)
    else:
        fg_clip = clip.resized(height=bg_height)
        
    # Create the background clip (zoomed in to fill)
    if clip_aspect > target_aspect:
        bg_clip = clip.resized(height=bg_height)
        x_center = bg_clip.w / 2
        bg_clip = bg_clip.cropped(x1=x_center - bg_width/2, y1=0, x2=x_center + bg_width/2, y2=bg_height)
    else:
        bg_clip = clip.resized(width=bg_width)
        y_center = bg_clip.h / 2
        bg_clip = bg_clip.cropped(x1=0, y1=y_center - bg_height/2, x2=bg_width, y2=y_center + bg_height/2)
        
    # Apply fast blur to background using OpenCV
    def blur_frame(image):
        # Downscale -> blur -> upscale for speed
        small = cv2.resize(image, (bg_width//10, bg_height//10))
        blurred = cv2.GaussianBlur(small, (15, 15), 0)
        return cv2.resize(blurred, (bg_width, bg_height))
        
    bg = bg_clip.image_transform(blur_frame)
    
    # Composite the foreground clip in the center of the blurred background
    return CompositeVideoClip([bg, fg_clip.with_position("center")])

def render_clip(video_path: str, start_time: float, end_time: float, transcript_words: list, output_path: str, font_name: str = "Montserrat-Black.ttf", destination: str = "TikTok"):
    """
    Renders a single clip, fitted to the destination aspect ratio, with animated captions.
    """
    try:
        # Load the subclip
        clip = VideoFileClip(video_path).subclipped(start_time, end_time)
        
        # 1. Fit to Destination Aspect Ratio with blurred background
        fitted_clip = fit_to_aspect_ratio_blurred_bg(clip, destination)
        
        # 2. Add Captions
        # Filter words that fall within this clip
        clip_words = [w for w in transcript_words if w['start'] >= start_time and w['end'] <= end_time]
        
        # Resolve font path
        font_path = os.path.abspath(os.path.join("..", "fonts", font_name))
        if not os.path.exists(font_path):
            font_path = "Arial" # fallback
            
        text_clips = []
        for w in clip_words:
            # Shift timestamps relative to the clip start
            rel_start = w['start'] - start_time
            rel_end = w['end'] - start_time
            
            # Text styling: White text, black highlight (stroke)
            txt_clip = TextClip(text=w['word'].upper(), font=font_path, font_size=110, color='white',
                                stroke_color='black', stroke_width=5, method='caption', size=(int(fitted_clip.w * 0.8), None))
            
            # Position lowered so it's not in the main video focus
            txt_clip = txt_clip.with_position(('center', int(fitted_clip.h * 0.75))).with_start(rel_start).with_end(rel_end)
            text_clips.append(txt_clip)
            
        final_video = CompositeVideoClip([fitted_clip] + text_clips)
        
        # Write out (fast)
        final_video.write_videofile(output_path, codec='libx264', audio_codec='aac', fps=24, preset='ultrafast', threads=4, logger=None)
        return output_path
        
    except Exception as e:
        print(f"Error rendering clip: {e}")
        return None
