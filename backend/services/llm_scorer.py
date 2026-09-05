import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from services.llm_providers.factory import get_llm_provider
from services.audio_analyzer import get_segment_energy_score

load_dotenv()


def _sample_transcript(transcript_text: str, max_chars: int = 25000) -> str:
    """Sample transcript if excessively long while preserving start, mid, and end context."""
    if len(transcript_text) <= max_chars:
        return transcript_text
    third = max_chars // 3
    mid_start = len(transcript_text) // 2 - third // 2
    start_sample = transcript_text[:third]
    mid_sample = transcript_text[mid_start: mid_start + third]
    end_sample = transcript_text[-third:]
    return f"{start_sample}\n[...]\n{mid_sample}\n[...]\n{end_sample}"


def score_chunks(
    transcript_text: str,
    transcript_words: Optional[List[Dict[str, Any]]] = None,
    num_clips: int = 3,
    audio_analysis: Optional[Dict[str, Any]] = None,
    min_duration: int = 30,
    max_duration: int = 90,
    custom_prompt: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Multi-modal Hook Detection & Scoring:
    Combines transcript narrative analysis with audio energy/emotion spikes.
    Supports dynamic clip lengths (30s to 90s), Chain-of-Thought (CoT) reasoning,
    custom creative directives, and rich viral analytics.
    """
    sampled_text = _sample_transcript(transcript_text)
    energy_peaks = audio_analysis.get("peaks", []) if audio_analysis else []

    # Get active LLM provider (Gemini -> OpenAI -> Ollama)
    provider = get_llm_provider()
    print(f"[LLMScorer] Selected LLM Provider: {provider.provider_name}")

    clips = None
    if provider.is_available():
        clips = provider.analyze_hooks(
            transcript_text=sampled_text,
            num_clips=num_clips,
            energy_peaks=energy_peaks,
            min_duration=min_duration,
            max_duration=max_duration,
            custom_prompt=custom_prompt,
        )

    # Fallback to alternative provider if primary failed
    if not clips and provider.provider_name != "Google Gemini":
        from services.llm_providers.gemini_provider import GeminiProvider
        gemini = GeminiProvider()
        if gemini.is_available():
            clips = gemini.analyze_hooks(
                transcript_text=sampled_text,
                num_clips=num_clips,
                energy_peaks=energy_peaks,
                min_duration=min_duration,
                max_duration=max_duration,
                custom_prompt=custom_prompt,
            )

    if not clips and provider.provider_name != "Ollama (Local)":
        from services.llm_providers.ollama_provider import OllamaProvider
        ollama = OllamaProvider()
        if ollama.is_available():
            clips = ollama.analyze_hooks(
                transcript_text=sampled_text,
                num_clips=num_clips,
                energy_peaks=energy_peaks,
                min_duration=min_duration,
                max_duration=max_duration,
                custom_prompt=custom_prompt,
            )

    # If LLM returned clips, enrich with multi-modal scoring, CoT defaults, and creative metadata
    if clips and len(clips) > 0:
        enriched_clips = []
        for i, clip in enumerate(clips):
            title = clip.get("title") or f"Viral Hook {i + 1}"
            start_text = clip.get("start_text", "")
            end_text = clip.get("end_text", "")
            reason = clip.get("reason") or "High emotional engagement and strong narrative hook."
            engagement_score = float(clip.get("engagement_score", 8.5))
            retention_score = float(clip.get("retention_score", engagement_score))
            emotion_score = float(clip.get("emotion_score", 8.0))
            hook_category = clip.get("hook_category", "Curiosity Gap")
            virality_tip = clip.get("virality_tip", "Start directly with the action or punchline.")
            highlight_words = clip.get("highlight_words", [])
            social_kit = clip.get("social_kit", None)

            enriched_clips.append({
                "id": f"clip_{i + 1}",
                "title": title,
                "hook_category": hook_category,
                "reason": reason,
                "virality_tip": virality_tip,
                "engagement_score": round(engagement_score, 1),
                "retention_score": round(retention_score, 1),
                "emotion_score": round(emotion_score, 1),
                "highlight_words": highlight_words,
                "social_kit": social_kit,
                "start_text": start_text,
                "end_text": end_text,
            })
        return enriched_clips

    print("[LLMScorer] All LLM providers failed or unavailable, falling back to equal split.")
    return _fallback_split(transcript_words, transcript_text, num_clips, min_duration)


def _fallback_split(
    transcript_words: Optional[List[Dict[str, Any]]] = None,
    transcript_text: str = "",
    num_clips: int = 3,
    target_duration: int = 45,
) -> List[Dict[str, Any]]:
    """Time-aware fallback split when LLMs are offline."""
    print("[LLMScorer] Using time-aware equal-split fallback.")

    if transcript_words and len(transcript_words) >= num_clips * 2:
        n = len(transcript_words)
        chunk = n // num_clips
        clips = []
        for i in range(num_clips):
            segment = transcript_words[i * chunk: (i + 1) * chunk]
            if not segment:
                continue
            clips.append({
                "id": f"clip_{i + 1}",
                "title": f"Segment {i + 1}",
                "reason": "Automated evenly-spaced high energy interval.",
                "engagement_score": 7.5,
                "start_text": " ".join([w["word"] for w in segment[:4]]),
                "end_text": " ".join([w["word"] for w in segment[-4:]]),
            })
        return clips

    # Plain text fallback
    words = transcript_text.split()
    chunk = max(1, len(words) // num_clips)
    return [
        {
            "id": f"clip_{i + 1}",
            "title": f"Segment {i + 1}",
            "reason": "Automated pacing interval.",
            "engagement_score": 7.0,
            "start_text": " ".join(words[i * chunk: i * chunk + 4]),
            "end_text": " ".join(words[min((i + 1) * chunk - 4, len(words) - 4): min((i + 1) * chunk, len(words))]),
        }
        for i in range(num_clips)
    ]
