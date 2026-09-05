import os
import requests
from typing import List, Dict, Any, Optional
from services.llm_providers.base import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    """Local Ollama LLM Provider supporting local models (qwen2.5, qwen3, llama3.2, etc.)."""

    def __init__(self):
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.preferred_models = [
            "qwen2.5:3b",
            "qwen3:4b",
            "llama3.2:3b",
            "phi4-mini",
            "mistral:7b",
        ]

    @property
    def provider_name(self) -> str:
        return "Ollama (Local)"

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.ollama_url}/", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def _get_active_model(self) -> str:
        try:
            r = requests.get(f"{self.ollama_url}/api/tags", timeout=3)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                for pref in self.preferred_models:
                    pref_base = pref.split(":")[0]
                    for m in models:
                        if pref_base in m:
                            return m
                if models:
                    return models[0]
        except Exception:
            pass
        return self.preferred_models[0]

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

        model_name = self._get_active_model()
        print(f"[OllamaProvider] Using model: {model_name}")

        prompt = f"""Find EXACTLY {num_clips} highly engaging viral hook segments from different parts of the transcript.
Each clip should be a complete self-contained thought between {min_duration} and {max_duration} seconds (80-180 words).

Return JSON in this EXACT schema:
{{
  "clips": [
    {{
      "title": "<Catchy Hook Title>",
      "reason": "<Why this moment is viral>",
      "engagement_score": 9.0,
      "start_text": "<First 4-8 words verbatim from transcript>",
      "end_text": "<Last 4-8 words verbatim from transcript>"
    }}
  ]
}}

Transcript:
{transcript_text[:12000]}"""

        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a viral short-form video editor. Your ONLY job is to output a valid JSON object with the requested clips."
                },
                {"role": "user", "content": prompt}
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 600}
        }

        try:
            resp = requests.post(f"{self.ollama_url}/api/chat", json=payload, timeout=60)
            if resp.status_code == 200:
                output_text = resp.json().get("message", {}).get("content", "").strip()
                return self.parse_llm_json(output_text)
        except Exception as e:
            print(f"[OllamaProvider] Error calling Ollama: {e}")

        return None
