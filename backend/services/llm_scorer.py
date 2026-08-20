import os
import json
import requests
from llama_cpp import Llama

# Qwen3-4B-Instruct Q4_K_M — better instruction following, ~2.6 GB, same family
MODEL_URL = "https://huggingface.co/bartowski/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf"
MODEL_PATH = "models/Qwen3-4B-Q4_K_M.gguf"

llm = None


def download_model_if_needed():
    if not os.path.exists("models"):
        os.makedirs("models")

    if os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) < 100_000_000:
        print("Model file is corrupted or incomplete. Deleting and re-downloading...")
        os.remove(MODEL_PATH)

    if not os.path.exists(MODEL_PATH):
        print(f"Downloading Qwen3-4B model ({MODEL_URL.split('/')[-1]}). This may take a few minutes...")
        response = requests.get(MODEL_URL, stream=True)
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0
        with open(MODEL_PATH, "wb") as f:
            for chunk in response.iter_content(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(f"\r  Downloading... {pct}%", end="", flush=True)
        print("\nModel downloaded successfully!")


def get_llm():
    global llm
    if llm is None:
        download_model_if_needed()
        # n_ctx=4096 gives Qwen3 more room for longer transcripts
        # n_threads=0 → use all CPU cores
        llm = Llama(
            model_path=MODEL_PATH,
            n_ctx=4096,
            n_threads=0,
            verbose=False,
        )
    return llm


def score_chunks(transcript_text: str):
    """
    Pass the transcript to Qwen3-4B and ask it to identify 3 distinct 60-second hooks.
    Returns a list of dicts: [{title, start_text, end_text}, ...]
    """
    llm_instance = get_llm()

    # Qwen3 chat format — /no_think disables the <think> reasoning block
    # so we get pure JSON output immediately without wasted tokens.
    system_msg = (
        "You are an expert video editor AI. Your ONLY job is to output valid JSON. "
        "Do not write any explanation, markdown, or text outside the JSON array."
    )

    user_msg = f"""/no_think
Find EXACTLY 3 highly engaging segments (hooks) in the transcript below for short-form social video.
The 3 clips MUST come from completely different, distinct parts of the video.
Each clip should be approximately 60 seconds long (~120-150 words).

Respond ONLY with a valid JSON array of exactly 3 objects. No other text.
Format:
[
  {{
    "title": "<Catchy Title>",
    "start_text": "<First 4 words of the clip, exactly as in the transcript>",
    "end_text": "<Last 4 words of the clip, exactly as in the transcript>"
  }}
]

Transcript:
{transcript_text[:3000]}"""

    response = llm_instance.create_chat_completion(
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=512,
        temperature=0.3,
        stop=["```"],
    )

    output_text = response["choices"][0]["message"]["content"].strip()

    print("\n--- RAW LLM OUTPUT ---")
    print(output_text)
    print("----------------------\n")

    # Parse JSON — be tolerant of leading/trailing text
    try:
        start_idx = output_text.find("[")
        end_idx = output_text.rfind("]") + 1
        if start_idx != -1 and end_idx > start_idx:
            clips = json.loads(output_text[start_idx:end_idx])
            if isinstance(clips, list) and len(clips) > 0:
                return clips
        # Try direct parse if no array brackets found wrapping
        clips = json.loads(output_text)
        return clips
    except Exception as e:
        print("Failed to parse LLM response:", str(e))
        # Fallback: split transcript into 3 equal chunks
        words = transcript_text.split()
        chunk = len(words) // 3
        return [
            {
                "title": f"Hook {i + 1}",
                "start_text": " ".join(words[i * chunk: i * chunk + 4]),
                "end_text": " ".join(words[min((i + 1) * chunk - 4, len(words) - 4): min((i + 1) * chunk, len(words))]),
            }
            for i in range(3)
        ]
