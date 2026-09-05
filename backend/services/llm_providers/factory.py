import os
from typing import Optional, List, Dict, Any
from services.llm_providers.base import BaseLLMProvider
from services.llm_providers.gemini_provider import GeminiProvider
from services.llm_providers.ollama_provider import OllamaProvider
from services.llm_providers.openai_provider import OpenAIProvider


def get_llm_provider(name: Optional[str] = None) -> BaseLLMProvider:
    """
    Factory function returning the configured or best available LLM provider.
    Priority:
      1. Explicitly requested provider (via argument or LLM_PROVIDER env var)
      2. GeminiProvider (if GEMINI_API_KEY configured)
      3. OpenAIProvider (if OPENAI_API_KEY / GROQ_API_KEY configured)
      4. OllamaProvider (if Ollama running locally)
      5. GeminiProvider as default
    """
    provider_choice = (name or os.getenv("LLM_PROVIDER", "auto")).lower()

    if provider_choice == "gemini":
        return GeminiProvider()
    elif provider_choice in ("openai", "groq"):
        return OpenAIProvider()
    elif provider_choice == "ollama":
        return OllamaProvider()

    # Auto mode: select best available
    gemini = GeminiProvider()
    if gemini.is_available():
        return gemini

    openai = OpenAIProvider()
    if openai.is_available():
        return openai

    ollama = OllamaProvider()
    if ollama.is_available():
        return ollama

    # Fallback to Gemini
    return gemini


def list_available_providers() -> List[Dict[str, Any]]:
    """Return status of all registered providers for UI inspection."""
    providers = [
        GeminiProvider(),
        OpenAIProvider(),
        OllamaProvider(),
    ]
    active = get_llm_provider()
    return [
        {
            "name": p.provider_name,
            "available": p.is_available(),
            "is_active": p.provider_name == active.provider_name,
        }
        for p in providers
    ]
