import os
import urllib.request
from llama_cpp import Llama
import json

MODEL_URL = "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
MODEL_PATH = "models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"

llm = None

import requests
def download_model_if_needed():
    if not os.path.exists("models"):
        os.makedirs("models")
        
    if os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) < 100000000:
        print("Model file is corrupted or incomplete. Deleting and redownloading...")
        os.remove(MODEL_PATH)

    if not os.path.exists(MODEL_PATH):
        print("Downloading TinyLlama model for CPU inference. This may take a few minutes...")
        response = requests.get(MODEL_URL, stream=True)
        response.raise_for_status()
        with open(MODEL_PATH, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print("Model downloaded successfully!")

def get_llm():
    global llm
    if llm is None:
        download_model_if_needed()
        # Using n_ctx=2048 to fit reasonably large transcript chunks
        llm = Llama(model_path=MODEL_PATH, n_ctx=2048, verbose=False)
    return llm

def score_chunks(transcript_text: str):
    """
    Pass the transcript to the LLM and ask it to find 15-60 second clips.
    Returns a list of clips with start_text, end_text, and a hook_title.
    """
    llm_instance = get_llm()
    
    prompt = f"""<|system|>
You are an AI video editor. Find EXACTLY 3 highly engaging segments (hooks) in the transcript for TikToks.
Ensure the 3 clips are from completely different, distinct parts of the video.
Each clip MUST be approximately 60 seconds long (about 120-150 words).
Respond ONLY with a valid JSON array containing exactly 3 objects. Do not add any conversational text.
Example format:
[
  {{
    "title": "The Crazy Secret",
    "start_text": "This is exactly why",
    "end_text": "you won't believe it."
  }},
  {{
    "title": "Another Great Hook",
    "start_text": "But wait, there's more",
    "end_text": "to the story."
  }},
  {{
    "title": "Mind Blown",
    "start_text": "The final truth is",
    "end_text": "what happens next."
  }}
]
</s>
<|user|>
Transcript:
{transcript_text[:1500]}
</s>
<|assistant|>
[
  {{
    "title":"""

    response = llm_instance(prompt, max_tokens=300, stop=["</s>"], temperature=0.3)
    
    # Re-attach the pre-filled start to the output text
    output_text = '[\n  {\n    "title":' + response['choices'][0]['text'].strip()
    
    print("\n--- RAW LLM OUTPUT ---")
    print(output_text)
    print("----------------------\n")
    
    # Try to parse the output as JSON
    try:
        # Find the JSON array inside the output in case the LLM added conversational text
        start_idx = output_text.find('[')
        end_idx = output_text.rfind(']') + 1
        if start_idx != -1 and end_idx != -1:
            json_str = output_text[start_idx:end_idx]
            clips = json.loads(json_str)
            return clips
        else:
            return []
    except json.JSONDecodeError:
        print("Failed to parse LLM response as JSON:", output_text)
        return []
