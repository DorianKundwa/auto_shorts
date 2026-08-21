import json
import requests

OLLAMA_URL = "http://localhost:11434"
# Preferred models in priority order
PREFERRED_MODELS = [
    "qwen2.5:3b",
    "qwen3:4b",
    "llama3.2:3b",
    "phi4-mini",
    "mistral:7b",
]


def _ollama_running() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _get_active_model() -> str:
    """Return the best available model pulled in Ollama."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code != 200:
            return PREFERRED_MODELS[0]
        models = [m["name"] for m in r.json().get("models", [])]
        for pref in PREFERRED_MODELS:
            pref_base = pref.split(":")[0]
            for m in models:
                if pref_base in m:
                    return m
        # If any other model exists, use it
        if models:
            return models[0]
    except Exception:
        pass
    return PREFERRED_MODELS[0]


def _sample_transcript(transcript_text: str, max_chars: int = 4000) -> str:
    """
    Fix #4: Sample evenly from start, middle and end of the transcript so the
    LLM analyses content from across the full video, not just the first ~2 minutes.
    """
    if len(transcript_text) <= max_chars:
        return transcript_text
    third = max_chars // 3
    mid_start = len(transcript_text) // 2 - third // 2
    start_sample = transcript_text[:third]
    mid_sample = transcript_text[mid_start: mid_start + third]
    end_sample = transcript_text[-third:]
    return f"{start_sample}\n[...]\n{mid_sample}\n[...]\n{end_sample}"


def score_chunks(transcript_text: str, transcript_words: list = None, num_clips: int = 3):
    """
    Ask Ollama to identify num_clips distinct ~60-second hooks in the transcript.
    Returns a list of dicts: [{title, start_text, end_text}, ...]
    transcript_words — optional word list with timestamps, used by the fallback
                       to produce time-accurate splits instead of word-count splits.
    """
    if not _ollama_running():
        print("[LLM] Ollama is not running on localhost:11434, using equal-split fallback.")
        return _fallback_split(transcript_words, transcript_text, num_clips)

    model_name = _get_active_model()
    print(f"[LLM] Using Ollama model: {model_name}")

    # Fix #4: sample across the full video instead of blindly truncating
    sampled_text = _sample_transcript(transcript_text)

    system_prompt = (
        "You are an expert viral video editor AI. Your ONLY job is to output a valid JSON object. "
        "Do not include any explanation or markdown formatting."
    )

    # Build the clips schema block dynamically for num_clips
    schema_items = []
    for i in range(1, num_clips + 1):
        schema_items.append(
            f'    {{\n'
            f'      "title": "<Catchy Title {i}>",\n'
            f'      "start_text": "<First 4 words of clip {i} from the transcript>",\n'
            f'      "end_text": "<Last 4 words of clip {i} from the transcript>"\n'
            f'    }}'
        )
    schema_block = ",\n".join(schema_items)

    user_prompt = f"""Find EXACTLY {num_clips} highly engaging ~60-second segments (hooks) from completely different parts of the transcript below.
Each clip should be around 120-150 words.

Return JSON in this EXACT schema:
{{
  "clips": [
{schema_block}
  ]
}}

Transcript:
{sampled_text}"""

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 400,
        },
    }

    try:
        # Fix #10: 180s timeout — local 4B models can take >60s on CPU-only machines
        resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=180)
        resp.raise_for_status()
        output_text = resp.json()["message"]["content"].strip()
    except requests.exceptions.Timeout:
        print("[LLM] Ollama request timed out after 180s, using equal-split fallback.")
        return _fallback_split(transcript_words, transcript_text, num_clips)
    except Exception as e:
        print(f"[LLM] Ollama chat request failed: {e}")
        return _fallback_split(transcript_words, transcript_text, num_clips)

    print("\n--- RAW LLM OUTPUT ---")
    print(output_text)
    print("----------------------\n")

    # Strip thinking blocks if present (e.g. qwen3 reasoning models)
    if "</think>" in output_text:
        output_text = output_text.split("</think>")[-1].strip()

    try:
        data = json.loads(output_text)
        if isinstance(data, dict) and "clips" in data and isinstance(data["clips"], list):
            if len(data["clips"]) > 0:
                return data["clips"]
        elif isinstance(data, list) and len(data) > 0:
            return data
    except Exception as e:
        print(f"[LLM] JSON parse error: {e}")

    # Fallback: find [ ... ] array inside text
    try:
        start = output_text.find("[")
        end = output_text.rfind("]") + 1
        if start != -1 and end > start:
            clips = json.loads(output_text[start:end])
            if isinstance(clips, list) and len(clips) > 0:
                return clips
    except Exception:
        pass

    return _fallback_split(transcript_words, transcript_text, num_clips)


def _fallback_split(transcript_words: list = None, transcript_text: str = "", num_clips: int = 3):
    """
    Fix #8: Split transcript into num_clips equal chunks.
    Uses word timestamps when available so chunks reflect real time boundaries.
    """
    print("[LLM] Using equal-split fallback.")

    if transcript_words and len(transcript_words) >= num_clips * 2:
        n = len(transcript_words)
        chunk = n // num_clips
        clips = []
        for i in range(num_clips):
            segment = transcript_words[i * chunk: (i + 1) * chunk]
            if not segment:
                continue
            clips.append({
                "title": f"Hook {i + 1}",
                "start_text": " ".join([w["word"] for w in segment[:4]]),
                "end_text":   " ".join([w["word"] for w in segment[-4:]]),
            })
        return clips

    # Plain-text fallback (no timestamps available)
    words = transcript_text.split()
    chunk = max(1, len(words) // num_clips)
    return [
        {
            "title":      f"Hook {i + 1}",
            "start_text": " ".join(words[i * chunk: i * chunk + 4]),
            "end_text":   " ".join(words[min((i + 1) * chunk - 4, len(words) - 4): min((i + 1) * chunk, len(words))]),
        }
        for i in range(num_clips)
    ]
