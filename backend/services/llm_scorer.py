import json
import requests

# ─── Ollama config ────────────────────────────────────────────────────────────
OLLAMA_URL   = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:4b"   # change to "phi4-mini" etc. if preferred


def _ollama_running() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _model_available() -> bool:
    """Check if OLLAMA_MODEL has been pulled."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        # Ollama normalises names; match on the base name
        base = OLLAMA_MODEL.split(":")[0]
        return any(base in m for m in models)
    except Exception:
        return False


def score_chunks(transcript_text: str):
    """
    Ask Ollama (Qwen3:4b) to identify 3 distinct ~60-second hooks in the
    transcript. Returns a list: [{title, start_text, end_text}, ...]

    Uses Ollama's OpenAI-compatible /v1/chat/completions endpoint so no
    extra SDK is needed — just the `requests` library that's already installed.
    """
    if not _ollama_running():
        raise RuntimeError(
            "Ollama is not running. Start it with: ollama serve"
        )

    if not _model_available():
        raise RuntimeError(
            f"Model '{OLLAMA_MODEL}' not pulled yet. Run: ollama pull {OLLAMA_MODEL}"
        )

    system_prompt = (
        "You are an expert viral video editor AI. "
        "Output ONLY valid JSON — no markdown, no explanation, nothing else."
    )

    user_prompt = f"""/no_think
Find EXACTLY 3 highly engaging ~60-second segments (hooks) from completely \
different parts of the transcript below. Each should be ~120-150 words long.

Return ONLY a JSON array of exactly 3 objects. No other text.
[
  {{
    "title": "<catchy viral title>",
    "start_text": "<first 4 words of the segment, exactly as in transcript>",
    "end_text": "<last 4 words of the segment, exactly as in transcript>"
  }}
]

Transcript:
{transcript_text[:4000]}"""

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 512,
        },
    }

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        output_text = resp.json()["message"]["content"].strip()
    except Exception as e:
        print(f"[LLM] Ollama request failed: {e}")
        return _fallback_split(transcript_text)

    print("\n--- RAW LLM OUTPUT ---")
    print(output_text)
    print("----------------------\n")

    # Strip optional <think>...</think> block that Qwen3 may emit
    if "<think>" in output_text and "</think>" in output_text:
        output_text = output_text[output_text.rfind("</think>") + len("</think>"):].strip()

    try:
        start = output_text.find("[")
        end   = output_text.rfind("]") + 1
        if start != -1 and end > start:
            clips = json.loads(output_text[start:end])
            if isinstance(clips, list) and len(clips) > 0:
                return clips
    except Exception as e:
        print(f"[LLM] JSON parse error: {e}")

    return _fallback_split(transcript_text)


def _fallback_split(transcript_text: str):
    """Split transcript into 3 equal chunks as a last-resort fallback."""
    print("[LLM] Using equal-split fallback.")
    words = transcript_text.split()
    chunk = max(1, len(words) // 3)
    return [
        {
            "title": f"Hook {i + 1}",
            "start_text": " ".join(words[i * chunk: i * chunk + 4]),
            "end_text":   " ".join(words[min((i + 1) * chunk - 4, len(words) - 4):
                                         min((i + 1) * chunk, len(words))]),
        }
        for i in range(3)
    ]
