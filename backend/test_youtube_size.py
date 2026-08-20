import os
from moviepy import ColorClip
from services.video_processor import fit_to_aspect_ratio_blurred_bg

def test():
    print("Testing TikTok aspect ratio...")
    clip_tiktok = fit_to_aspect_ratio_blurred_bg(ColorClip(size=(1280, 720), color=(255, 0, 0), duration=1), "TikTok")
    print(f"TikTok output size: {clip_tiktok.w}x{clip_tiktok.h}")

    print("Testing YouTube aspect ratio...")
    clip_youtube = fit_to_aspect_ratio_blurred_bg(ColorClip(size=(1280, 720), color=(255, 0, 0), duration=1), "YouTube")
    print(f"YouTube output size: {clip_youtube.w}x{clip_youtube.h}")

if __name__ == "__main__":
    test()
