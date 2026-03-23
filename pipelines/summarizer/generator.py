import json
import re
from pathlib import Path
from typing import Dict, Any

from pipelines.summarizer.cache import DiskCache
from pipelines.summarizer.config import load_config
from models.data_model import EmailDoc
from pipelines.summarizer.ollama_local import LocalOllama, OllamaSettings
from logging_utils import setup_logging

# Setup structured logging
logger = setup_logging("summarizer.generator")
CFG = load_config()

class Generator:
    """
    Handles LLM summarization generation.
    """
    def __init__(self) -> None:
        self._disk_cache = None
        if CFG.get("cache_enabled", False):
            self._disk_cache = DiskCache(
                cache_dir=Path(CFG.get("cache_dir", ".cache")),
                ttl_seconds=int(CFG.get("cache_ttl_seconds", 3600)),
                max_entries=int(CFG.get("cache_max_entries", 1000)),
            )
        self._llm = LocalOllama(
            OllamaSettings(
                host=str(CFG.get("ollama_host", "http://127.0.0.1:11434")),
                timeout_seconds=float(CFG.get("ollama_timeout_seconds", 120)),
                keep_alive=CFG.get("ollama_keep_alive"),
                num_retries=int(CFG.get("ollama_num_retries", 0)),
                retry_backoff_seconds=float(CFG.get("ollama_retry_backoff_seconds", 0.5)),
                offline=bool(CFG.get("offline", True)),
            )
        )
        # Load prompt template
        self._prompt_template = Path(CFG["prompt_path"]).read_text(encoding="utf-8")

    def generate(self, email: EmailDoc, learned_instructions: str = "") -> Dict[str, Any]:
        """Generate a summary for the given email."""
        # Preparation
        prompt = self._prompt_template.replace("{{email_text}}", email.text)
        if learned_instructions:
            prompt = learned_instructions + "\n\n" + prompt

        # Cache check
        cache_key = None
        if self._disk_cache:
            cache_key = self._disk_cache.make_key(
                namespace="generate",
                model=str(CFG.get("llm")),
                user=prompt
            )
            cached = self._disk_cache.get(cache_key)
            if isinstance(cached, dict) and cached:
                return cached

        # LLM Call
        raw = self._llm.chat_json(
            model=str(CFG.get("llm")),
            system="You are a professional email assistant. Return ONLY valid JSON.",
            user=prompt,
            options={"temperature": 0.1, "num_predict": CFG.get("num_predict", 512)}
        )

        # Parse and return
        try:
            result = json.loads(raw)
        except Exception:
            # Fallback to regex extraction if JSON is malformed
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            result = json.loads(match.group()) if match else {}

        if result and self._disk_cache and cache_key:
            self._disk_cache.set(cache_key, result)

        return result
