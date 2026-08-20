from moviepy import TextClip

try:
    font_path = r'c:\Users\admin\Documents\auto_shorts\fonts\Montserrat-Black.ttf'
    clip = TextClip(text="YgT!", font=font_path, font_size=110, color='white', stroke_color='black', stroke_width=5, margin=(20, 20))
    print("Success! Size:", clip.size)
except Exception as e:
    import traceback
    traceback.print_exc()
