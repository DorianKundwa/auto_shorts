import os
from moviepy import VideoFileClip, TextClip, CompositeVideoClip, ColorClip

def fit_to_aspect_ratio_white_bg(clip: VideoFileClip, destination: str):
    """
    Fits a standard video to the appropriate aspect ratio based on destination.
    Fills the background with white color.
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
        
    # Maintain aspect ratio while fitting into the bounding box
    clip_aspect = clip.w / clip.h
    target_aspect = bg_width / bg_height
    
    if clip_aspect > target_aspect:
        # Clip is wider than target, fit to width
        resized_clip = clip.resized(width=bg_width)
    else:
        # Clip is taller than target, fit to height
        resized_clip = clip.resized(height=bg_height)
    
    # Create white background
    bg = ColorClip(size=(bg_width, bg_height), color=(255, 255, 255)).with_duration(clip.duration)
    
    # Composite the resized clip in the center of the background
    return CompositeVideoClip([bg, resized_clip.with_position("center")])

def render_clip(video_path: str, start_time: float, end_time: float, transcript_words: list, output_path: str, font_name: str = "Montserrat-Black.ttf", destination: str = "TikTok"):
    """
    Renders a single clip, fitted to the destination aspect ratio, with animated captions.
    """
    try:
        # Load the subclip
        clip = VideoFileClip(video_path).subclipped(start_time, end_time)
        
        # 1. Fit to Destination Aspect Ratio with white background
        fitted_clip = fit_to_aspect_ratio_white_bg(clip, destination)
        
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
            
            # Text styling: White text, yellow highlight (stroke), positioned in the middle
            txt_clip = TextClip(text=w['word'].upper(), font=font_path, font_size=110, color='white',
                                stroke_color='yellow', stroke_width=5, method='caption', size=(fitted_clip.w * 0.8, None))
            
            # Position at the center middle
            txt_clip = txt_clip.with_position(('center', 'center')).with_start(rel_start).with_end(rel_end)
            text_clips.append(txt_clip)
            
        final_video = CompositeVideoClip([fitted_clip] + text_clips)
        
        # Write out
        final_video.write_videofile(output_path, codec='libx264', audio_codec='aac', fps=24, preset='ultrafast')
        return output_path
        
    except Exception as e:
        print(f"Error rendering clip: {e}")
        return None
