import os
import cv2
import mediapipe as mp
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from scenedetect import detect, ContentDetector

mp_face_detection = mp.solutions.face_detection

def find_face_center(frame):
    """
    Returns the x-coordinate of the center of the face in the frame.
    If no face is found, returns the center of the frame.
    """
    height, width, _ = frame.shape
    with mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5) as face_detection:
        # Convert the BGR image to RGB
        results = face_detection.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        
        if results.detections:
            # Assume the first face is the primary speaker
            detection = results.detections[0]
            bbox = detection.location_data.relative_bounding_box
            x_center = bbox.xmin + (bbox.width / 2)
            return int(x_center * width)
            
    return width // 2

def crop_to_9_16(clip: VideoFileClip):
    """
    Smart crop a standard 16:9 or similar video to 9:16 aspect ratio,
    attempting to keep the speaker centered.
    For simplicity and performance, we'll check the center once per second
    and interpolate, or just center on the most prominent face.
    """
    target_width = int(clip.h * 9 / 16)
    
    # Analyze the middle frame of the clip to find the face
    # (A more advanced version would track frame-by-frame or scene-by-scene)
    mid_time = clip.duration / 2
    frame = clip.get_frame(mid_time)
    
    face_x = find_face_center(frame)
    
    # Calculate crop coordinates
    x1 = max(0, face_x - target_width // 2)
    x2 = x1 + target_width
    
    # Ensure we don't go out of bounds
    if x2 > clip.w:
        x2 = clip.w
        x1 = x2 - target_width
        
    return clip.crop(x1=x1, y1=0, x2=x2, y2=clip.h).resize(height=1920, width=1080)

def render_clip(video_path: str, start_time: float, end_time: float, transcript_words: list, output_path: str):
    """
    Renders a single 15-60s clip, cropped to 9:16, with animated captions.
    """
    try:
        # Load the subclip
        clip = VideoFileClip(video_path).subclip(start_time, end_time)
        
        # 1. Smart Crop
        cropped_clip = crop_to_9_16(clip)
        
        # 2. Add Captions
        # Filter words that fall within this clip
        clip_words = [w for w in transcript_words if w['start'] >= start_time and w['end'] <= end_time]
        
        # Create TextClips for each word
        # In a real app, you'd group them by sentence or chunk. Here we do simple word-by-word flashing
        text_clips = []
        for w in clip_words:
            # Shift timestamps relative to the clip start
            rel_start = w['start'] - start_time
            rel_end = w['end'] - start_time
            
            # Simple text styling
            txt_clip = TextClip(w['word'], fontsize=80, color='white', font='Arial-Bold',
                                stroke_color='black', stroke_width=3, method='caption', size=(1000, None))
            
            txt_clip = txt_clip.set_position(('center', 'center')).set_start(rel_start).set_end(rel_end)
            text_clips.append(txt_clip)
            
        final_video = CompositeVideoClip([cropped_clip] + text_clips)
        
        # Write out
        final_video.write_videofile(output_path, codec='libx264', audio_codec='aac', fps=24, preset='ultrafast')
        return output_path
        
    except Exception as e:
        print(f"Error rendering clip: {e}")
        return None
