import os
from typing import Optional
from groq import Groq
from pipelines.summarizer.ollama_local import OllamaSettings
from logging_utils import setup_logging

logger = setup_logging("groq_llm")

class GroqLLM:
    def __init__(self):
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY required")
        self._client = Groq(api_key=api_key)
        self._model = os.environ.get("GROQ_MODEL", "llama3.1-8b-instant")
        logger.info("GroqLLM initialized")

    def chat_json(self, *, model: str, system: Optional[str], user: str, options: dict) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=1024,
        )
        return response.choices[0].message.content
