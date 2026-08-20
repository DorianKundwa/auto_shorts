from moviepy import TextClip

try:
    font_path = r'c:\Users\admin\Documents\auto_shorts\fonts\Montserrat-Black.ttf'
    clip = TextClip(text="THIS IS A LONG SENTENCE THAT SHOULD WRAP AROUND", font=font_path, font_size=70, color='white', method='caption', size=(900, None))
    print("Success! Size:", clip.size)
except Exception as e:
    import traceback
    traceback.print_exc()
