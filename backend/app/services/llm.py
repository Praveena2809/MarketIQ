"""
LLM Service abstraction utilizing Google's official GenAI SDK (google-genai).
Provides unified access to Gemini text generation and structured outputs for agents.
"""
from typing import Optional, Any
from google import genai
from google.genai import types

from app.core.config import get_settings


class LLMService:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        self._client: Optional[genai.Client] = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY is not configured in settings or environment.")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        """Generate text response using Gemini model."""
        config_kwargs = {"temperature": temperature}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        config = types.GenerateContentConfig(**config_kwargs)
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return response.text or ""

    def generate_json(
        self,
        prompt: str,
        schema: Optional[Any] = None,
        system_instruction: Optional[str] = None,
    ) -> str:
        """Generate structured JSON response using Gemini model."""
        config_kwargs = {"response_mime_type": "application/json"}
        if schema:
            config_kwargs["response_schema"] = schema
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        config = types.GenerateContentConfig(**config_kwargs)
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return response.text or ""


_llm_service_instance: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Singleton getter for LLMService."""
    global _llm_service_instance
    if _llm_service_instance is None:
        _llm_service_instance = LLMService()
    return _llm_service_instance
