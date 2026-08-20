import os
import requests
import time

model_path = r"c:\Users\admin\Documents\auto_shorts\backend\models\qwen2.5-3b-instruct-q4_k_m.gguf"
model_url = "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"

print("Starting robust resumable download...")
while True:
    headers = {}
    downloaded = 0
    if os.path.exists(model_path):
        downloaded = os.path.getsize(model_path)
        headers['Range'] = f'bytes={downloaded}-'
        print(f"Resuming download from {downloaded} bytes...")

    try:
        response = requests.get(model_url, headers=headers, stream=True, allow_redirects=True, timeout=10)
        if response.status_code == 416: # Range not satisfiable, file is fully downloaded
            print("File is already fully downloaded.")
            break
            
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0)) + downloaded
        print(f"Total target size: {total_size // (1024*1024)} MB")
        
        last_printed = -1
        with open(model_path, "ab" if downloaded > 0 else "wb") as f:
            for chunk in response.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = int(downloaded * 100 / total_size)
                        if percent % 5 == 0 and percent != last_printed:
                            print(f"Progress: {percent}% ({downloaded // (1024*1024)} MB)")
                            last_printed = percent
        
        if downloaded >= total_size:
            print("Download fully complete!")
            break

    except Exception as e:
        print(f"Network error: {e}. Retrying in 3 seconds...")
        time.sleep(3)
