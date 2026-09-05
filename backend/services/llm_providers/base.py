from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import json


class BaseLLMProvider(ABC):
    """Abstract Base Class for LLM Providers used in viral hook detection."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider credentials/server are available."""
        pass

    @abstractmethod
    def analyze_hooks(
        self,
        transcript_text: str,
        num_clips: int = 3,
        energy_peaks: Optional[List[Dict[str, Any]]] = None,
        min_duration: int = 30,
        max_duration: int = 90,
        custom_prompt: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Analyze transcript and audio energy spikes using Chain-of-Thought prompting.
        Returns list of clips with:
        [{
          "title": str,
          "reason": str,
          "engagement_score": float (1-10),
          "start_text": str,
          "end_text": str
        }]
        """
        pass

    @staticmethod
    def parse_llm_json(output_text: str) -> Optional[List[Dict[str, Any]]]:
        """Utility method to extract and parse JSON array of clips."""
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
                for key in ["clips", "segments", "hooks", "results", "viral_moments"]:
                    if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                        return data[key]
            elif isinstance(data, list) and len(data) > 0:
                return data
        except Exception:
            pass

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
