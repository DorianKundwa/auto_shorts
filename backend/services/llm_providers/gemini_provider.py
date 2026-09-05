import os
import requests
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from services.llm_providers.base import BaseLLMProvider

# Ensure .env variables (e.g. GEMINI_API_KEY, GEMINI_MODEL) are loaded
load_dotenv()


class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM Provider supporting Chain-of-Thought (CoT) hook extraction,
    virality scoring, creator tips, caption highlights, and social media kits."""

    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.models = [
            os.getenv("GEMINI_MODEL", "gemini-3.7-flash"),
            "gemini-3.8-flash",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-flash-latest",
        ]

    @property
    def provider_name(self) -> str:
        return "Google Gemini"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 5)

    def analyze_hooks(
        self,
        transcript_text: str,
        num_clips: int = 3,
        energy_peaks: Optional[List[Dict[str, Any]]] = None,
        min_duration: int = 30,
        max_duration: int = 90,
        custom_prompt: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        if not self.is_available():
            return None

        # Build audio energy context if available
        energy_context = ""
        if energy_peaks:
            peak_lines = [
                f"- {p.get('description', 'Volume/Emotion Spike')} at {p.get('start', 0)}s - {p.get('end', 0)}s (intensity {p.get('energy', 0.8)})"
                for p in energy_peaks[:6]
            ]
            energy_context = "\nAudio Analysis Detected Key Vocal / Emotional Energy Spikes:\n" + "\n".join(peak_lines) + "\n"

        directive_context = ""
        if custom_prompt and custom_prompt.strip():
            directive_context = f"\nCREATIVE FOCUS & USER DIRECTIVE:\n{custom_prompt.strip()}\n"

        prompt = f"""You are an elite viral video producer and TikTok/Shorts algorithm specialist.
Analyze the video transcript and audio energy context below using Chain-of-Thought (CoT) reasoning.

{energy_context}{directive_context}
Transcript:
{transcript_text}

TASK INSTRUCTIONS:
Step 1: Breakdown the transcript into distinct narrative acts, identifying tension, comedy, surprise, or profound insight.
Step 2: Cross-reference with the speaker's vocal/emotional peaks to locate the highest-impact moments.
Step 3: Select EXACTLY {num_clips} of the most viral, self-contained story segments.
- Each clip MUST be a natural, self-contained thought between {min_duration} and {max_duration} seconds in length (roughly 70 to 220 words). DO NOT force rigid lengths.
- 'start_text' MUST be the exact 4-8 words verbatim from the transcript where the hook begins.
- 'end_text' MUST be the exact 4-8 words verbatim from the transcript where the punchline/conclusion finishes.
- 'title' MUST be an ultra-engaging, click-worthy hook title (3-6 words, no hashtags, high curiosity).
- 'hook_category' MUST be one of: "Curiosity Gap", "High Humor", "Pattern Interrupt", "Actionable Wisdom", "Emotional Story", "Controversial Take".
- 'reason' MUST explain the psychological trigger and why this segment retains viewer attention.
- 'virality_tip' MUST give the creator a concrete recommendation for editing, pacing, or b-roll.
- 'engagement_score' MUST be a rating from 1.0 to 10.0 representing overall virality.
- 'retention_score' MUST be a rating from 1.0 to 10.0 representing cliffhanger/pacing strength.
- 'emotion_score' MUST be a rating from 1.0 to 10.0 representing emotional or vocal intensity.
- 'highlight_words' MUST be 3 to 6 high-impact punch words spoken in this segment to highlight in dynamic captions (e.g., ["INSANE", "NEVER", "EXPLODED", "SECRET"]).
- 'social_kit' MUST contain:
    - 'headline': Viral title for social post
    - 'caption': Engaging 2-3 sentence caption formatted for TikTok/Reels/Shorts with Call-To-Action
    - 'hashtags': 5 to 8 high-reach hashtags (e.g., ["#viral", "#shorts", "#mindblowing"])

Return JSON matching this schema:
{{
  "analysis": [
    {{"act": "Summary of Act 1", "viral_potential": 8.5, "notes": "Strong opening hook"}}
  ],
  "clips": [
    {{
      "title": "<Catchy Hook Title>",
      "hook_category": "Curiosity Gap",
      "reason": "<CoT explanation of viral appeal>",
      "virality_tip": "<Creator editing tip>",
      "engagement_score": 9.5,
      "retention_score": 9.2,
      "emotion_score": 8.8,
      "highlight_words": ["WORD1", "WORD2", "WORD3"],
      "social_kit": {{
        "headline": "<Social Headline>",
        "caption": "<Engaging Caption with CTA>",
        "hashtags": ["#shorts", "#viral", "#foryou"]
      }},
      "start_text": "<exact first 4 to 8 words verbatim from transcript>",
      "end_text": "<exact last 4 to 8 words verbatim from transcript>"
    }}
  ]
}}"""

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
            }
        }

        headers = {"Content-Type": "application/json"}

        for model_name in self.models:
            clean_model = model_name.replace("models/", "")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={self.api_key}"
            print(f"[GeminiProvider] Scoring with model: {clean_model}")

            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=40)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    candidates = resp_json.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            output_text = parts[0].get("text", "").strip()
                            clips = self.parse_llm_json(output_text)
                            if clips and len(clips) > 0:
                                print(f"[GeminiProvider] Extracted {len(clips)} viral clips successfully using {clean_model}.")
                                return clips
                elif resp.status_code in (400, 403):
                    print(f"[GeminiProvider] Auth/request error HTTP {resp.status_code}: {resp.text[:200]}")
                    break
                else:
                    print(f"[GeminiProvider] HTTP {resp.status_code} for {clean_model}: {resp.text[:200]}")
            except Exception as e:
                print(f"[GeminiProvider] Call failed for {clean_model}: {e}")

        return None

    def generate_social_kit(self, transcript_segment: str, title: str) -> Optional[Dict[str, Any]]:
        """Generate or re-generate an AI Social Media Kit for a specific clip."""
        if not self.is_available():
            return None

        prompt = f"""You are a top-tier social media manager specializing in TikTok, Instagram Reels, and YouTube Shorts.
Given this clip title and transcript segment, generate a viral social media posting kit.

Clip Title: {title}
Transcript Segment:
{transcript_segment}

Return JSON with:
{{
  "headline": "<Punchy title that stops the scroll>",
  "caption": "<Engaging 2-3 sentence caption with emojis and a provocative Call-To-Action encouraging comments>",
  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5", "#tag6"],
  "pinned_comment": "<Question or prompt to pin in the comment section to drive discussions>"
}}"""

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.3,
            }
        }
        headers = {"Content-Type": "application/json"}

        for model_name in self.models:
            clean_model = model_name.replace("models/", "")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={self.api_key}"
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=25)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    candidates = resp_json.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            import json
                            return json.loads(parts[0].get("text", "").strip())
            except Exception as e:
                print(f"[GeminiProvider] Social kit generation failed for {clean_model}: {e}")

        return None
