import os
import requests
from typing import List, Dict, Any, Optional
from services.llm_providers.base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    """OpenAI / Groq / DeepSeek compatible LLM Provider."""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY", "")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if os.getenv("GROQ_API_KEY") and not os.getenv("OPENAI_API_KEY"):
            self.base_url = "https://api.groq.com/openai/v1"
            self.model = os.getenv("OPENAI_MODEL", "llama-3.3-70b-versatile")
        else:
            self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    @property
    def provider_name(self) -> str:
        return "OpenAI / Groq"

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

        prompt = f"""You are an elite short-form video editor.
Analyze the transcript and identify EXACTLY {num_clips} viral hook segments between {min_duration} and {max_duration} seconds long.

Return JSON in this schema:
{{
  "clips": [
    {{
      "title": "<Catchy Hook Title>",
      "reason": "<CoT reason why this is viral>",
      "engagement_score": 9.5,
      "start_text": "<First 4-8 words verbatim from transcript>",
      "end_text": "<Last 4-8 words verbatim from transcript>"
    }}
  ]
}}

Transcript:
{transcript_text}"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a viral video editor. Output only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        try:
            resp = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                return self.parse_llm_json(content)
        except Exception as e:
            print(f"[OpenAIProvider] Call failed: {e}")

        return None
