import os
import requests
import time

MODEL_PATH = r"c:\Users\admin\Documents\auto_shorts\backend\models\Qwen3-4B-Q4_K_M.gguf"
MODEL_URL = "https://huggingface.co/bartowski/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf"

print(f"Downloading Qwen3-4B Q4_K_M (~2.6 GB) with resumable download...")

while True:
    headers = {}
    downloaded = 0
    if os.path.exists(MODEL_PATH):
        downloaded = os.path.getsize(MODEL_PATH)
        headers["Range"] = f"bytes={downloaded}-"
        print(f"Resuming from {downloaded // (1024*1024)} MB...")

    try:
        response = requests.get(MODEL_URL, headers=headers, stream=True, allow_redirects=True, timeout=15)
        if response.status_code == 416:
            print("File is already fully downloaded.")
            break

        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0)) + downloaded
        print(f"Total target size: {total_size // (1024*1024)} MB")

        last_printed = -1
        with open(MODEL_PATH, "ab" if downloaded > 0 else "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = int(downloaded * 100 / total_size)
                        if pct % 5 == 0 and pct != last_printed:
                            print(f"  Progress: {pct}% ({downloaded // (1024*1024)} MB / {total_size // (1024*1024)} MB)")
                            last_printed = pct

        if downloaded >= total_size:
            print("Download complete!")
            break

    except Exception as e:
        print(f"Network error: {e}. Retrying in 3 seconds...")
        time.sleep(3)
