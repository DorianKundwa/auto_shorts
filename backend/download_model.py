import requests
import os

model_path = r"c:\Users\admin\Documents\auto_shorts\backend\models\tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
model_url = "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"

if os.path.exists(model_path):
    os.remove(model_path)

print("Starting download using requests...")
response = requests.get(model_url, stream=True)
response.raise_for_status()

with open(model_path, "wb") as f:
    for chunk in response.iter_content(chunk_size=8192):
        f.write(chunk)
print("Download complete!")
