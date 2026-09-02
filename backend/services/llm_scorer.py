import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODELS = [
    os.getenv("GEMINI_MODEL", "gemini-3.7-flash"),
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
]

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
# Preferred Ollama models in priority order
OLLAMA_PREFERRED_MODELS = [
    "qwen2.5:3b",
    "qwen3:4b",
    "llama3.2:3b",
    "phi4-mini",
    "mistral:7b",
]


def _ollama_running() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _get_active_ollama_model() -> str:
    """Return the best available model pulled in Ollama."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if r.status_code != 200:
            return OLLAMA_PREFERRED_MODELS[0]
        models = [m["name"] for m in r.json().get("models", [])]
        for pref in OLLAMA_PREFERRED_MODELS:
            pref_base = pref.split(":")[0]
            for m in models:
                if pref_base in m:
                    return m
        # If any other model exists, use it
        if models:
            return models[0]
    except Exception:
        pass
    return OLLAMA_PREFERRED_MODELS[0]


def _sample_transcript(transcript_text: str, max_chars: int = 15000) -> str:
    """
    Sample transcript if excessively long while preserving start, middle, and end context.
    """
    if len(transcript_text) <= max_chars:
        return transcript_text
    third = max_chars // 3
    mid_start = len(transcript_text) // 2 - third // 2
    start_sample = transcript_text[:third]
    mid_sample = transcript_text[mid_start: mid_start + third]
    end_sample = transcript_text[-third:]
    return f"{start_sample}\n[...]\n{mid_sample}\n[...]\n{end_sample}"


def _parse_llm_json(output_text: str):
    """Robustly parse JSON clips list from LLM output."""
    if not output_text:
        return None

    # Strip reasoning / think tags if present
    if "</think>" in output_text:
        output_text = output_text.split("</think>")[-1].strip()

    # Strip markdown code fences if present
    if "```" in output_text:
        lines = output_text.split("\n")
        cleaned_lines = []
        inside_fence = False
        for line in lines:
            if line.strip().startswith("```"):
                inside_fence = not inside_fence
                continue
            cleaned_lines.append(line)
        output_text = "\n".join(cleaned_lines).strip()

    try:
        data = json.loads(output_text)
        if isinstance(data, dict):
            for key in ["clips", "segments", "hooks", "results"]:
                if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                    return data[key]
        elif isinstance(data, list) and len(data) > 0:
            return data
    except Exception as e:
        print(f"[LLM] Direct JSON parse failed: {e}")

    # Fallback: extract substring between [ and ]
    try:
        start = output_text.find("[")
        end = output_text.rfind("]") + 1
        if start != -1 and end > start:
            clips = json.loads(output_text[start:end])
            if isinstance(clips, list) and len(clips) > 0:
                return clips
    except Exception:
        pass

    return None


def _score_with_gemini(transcript_text: str, num_clips: int = 3):
    """
    Use Google Gemini API to identify viral hooks and clip timestamps/phrases.
    Returns list of dicts: [{title, start_text, end_text}, ...] or None if failed.
    """
    api_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
    if not api_key:
        return None

    sampled_text = _sample_transcript(transcript_text, max_chars=30000)

    schema_example = (
        '[\n'
        '  {\n'
        '    "title": "Viral Hook Title 1",\n'
        '    "start_text": "<exact first 4 to 8 words verbatim from transcript>",\n'
        '    "end_text": "<exact last 4 to 8 words verbatim from transcript>"\n'
        '  }\n'
        ']'
    )

    prompt = f"""You are an elite viral video editor creating YouTube Shorts and TikToks.
Analyze the transcript below and select EXACTLY {num_clips} of the most engaging, viral, high-retention segments (hooks) from different parts of the video.

CRITICAL REQUIREMENTS:
1. Each segment must be approximately 45-60 seconds long (roughly 120-160 words).
2. 'start_text' MUST be the exact 4-8 words from the transcript where the clip starts (exact verbatim wording).
3. 'end_text' MUST be the exact 4-8 words from the transcript where the clip ends (exact verbatim wording).
4. 'title' MUST be a punchy, click-worthy hook title for social media (3-6 words, no quotes or hashtags).
5. Output MUST be a valid JSON array matching this structure:
{schema_example}

Transcript:
{sampled_text}"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
        }
    }

    headers = {
        "Content-Type": "application/json"
    }

    # Iterate through Gemini models in priority order
    for model_name in GEMINI_MODELS:
        clean_model = model_name.replace("models/", "")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
        print(f"[LLM] Trying Gemini API model: {clean_model}")

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=25)
            if resp.status_code == 200:
                resp_json = resp.json()
                candidates = resp_json.get("candidates", [])
                if candidates:
                    first_cand = candidates[0]
                    content_parts = first_cand.get("content", {}).get("parts", [])
                    if content_parts:
                        output_text = content_parts[0].get("text", "").strip()
                        print("\n--- RAW GEMINI OUTPUT ---")
                        print(output_text[:600] + ("..." if len(output_text) > 600 else ""))
                        print("-------------------------\n")

                        clips = _parse_llm_json(output_text)
                        if clips and len(clips) > 0:
                            print(f"[LLM] Successfully extracted {len(clips)} clips with Gemini ({clean_model})")
                            return clips
            elif resp.status_code in (400, 403):
                # Bad API key or authorization error -> do not waste time retrying other models
                print(f"[LLM] Gemini API authentication/request error HTTP {resp.status_code}: {resp.text[:200]}")
                break
            else:
                print(f"[LLM] Gemini {clean_model} returned HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[LLM] Gemini API call to {clean_model} failed: {e}")

    return None


def _score_with_ollama(transcript_text: str, num_clips: int = 3):
    """
    Fallback to local Ollama if running.
    """
    if not _ollama_running():
        return None

    model_name = _get_active_ollama_model()
    print(f"[LLM] Using Ollama model: {model_name}")

    sampled_text = _sample_transcript(transcript_text, max_chars=4000)

    system_prompt = (
        "You are an expert viral video editor AI. Your ONLY job is to output a valid JSON object. "
        "Do not include any explanation or markdown formatting."
    )

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
        resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=60)
        resp.raise_for_status()
        output_text = resp.json()["message"]["content"].strip()
        print("\n--- RAW OLLAMA OUTPUT ---")
        print(output_text)
        print("-------------------------\n")
        return _parse_llm_json(output_text)
    except Exception as e:
        print(f"[LLM] Ollama chat request failed: {e}")
        return None


def score_chunks(transcript_text: str, transcript_words: list = None, num_clips: int = 3):
    """
    Identify num_clips distinct ~60-second viral hooks in the transcript.
    Priority:
      1. Google Gemini API (if GEMINI_API_KEY is configured)
      2. Ollama local LLM (if Ollama is running)
      3. Equal-split fallback
    Returns a list of dicts: [{title, start_text, end_text}, ...]
    """
    # 1. Try Google Gemini API
    if GEMINI_API_KEY or os.getenv("GEMINI_API_KEY"):
        clips = _score_with_gemini(transcript_text, num_clips=num_clips)
        if clips:
            return clips
        print("[LLM] Gemini API scoring was unsuccessful, attempting local Ollama fallback...")

    # 2. Try Ollama local LLM
    if _ollama_running():
        clips = _score_with_ollama(transcript_text, num_clips=num_clips)
        if clips:
            return clips
        print("[LLM] Ollama scoring was unsuccessful, falling back to equal-split.")
    else:
        print("[LLM] Ollama is not running on localhost:11434, using equal-split fallback.")

    # 3. Fallback equal split
    return _fallback_split(transcript_words, transcript_text, num_clips)


def _fallback_split(transcript_words: list = None, transcript_text: str = "", num_clips: int = 3):
    """
    Split transcript into num_clips equal chunks.
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
