import os
import urllib.request
from llama_cpp import Llama
import json

MODEL_URL = "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
MODEL_PATH = "models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"

llm = None

def download_model_if_needed():
    if not os.path.exists("models"):
        os.makedirs("models")
        
    if not os.path.exists(MODEL_PATH):
        print("Downloading TinyLlama model for CPU inference. This may take a few minutes...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
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
You are an expert video editor. I will give you a transcript.
Find 1-3 highly engaging segments (hooks) that make great 15-60 second TikToks.
Respond ONLY with a valid JSON array of objects, where each object has:
- "title": a catchy title for the clip
- "start_text": the first few words of the clip
- "end_text": the last few words of the clip

Return ONLY the JSON array, no other text.
</s>
<|user|>
Transcript:
{transcript_text[:1500]}  # Limiting length for this demo to avoid context window limits
</s>
<|assistant|>
"""

    response = llm_instance(prompt, max_tokens=300, stop=["</s>"], temperature=0.3)
    
    output_text = response['choices'][0]['text'].strip()
    
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
