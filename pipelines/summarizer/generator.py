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
        try:
            from pipelines.summarizer.groq_llm import GroqLLM
            self._llm = GroqLLM()
            logger.info("Using Groq LLM (Render)")
        except (ImportError, ValueError):
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
            logger.info("Using Ollama LLM (local)")
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
                system="You are a professional email assistant. Return ONLY valid JSON.",
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

        # Robust JSON Parse
        def extract_json(text: str) -> Dict[str, Any]:
            # Strip common wrappers
            text = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.IGNORECASE)
            text = re.sub(r'\n?```$', '', text, flags=re.IGNORECASE)
            text = text.strip()
            
            # Better regex for outermost JSON
            match = re.search(r'(\{.*\})', text, re.DOTALL)
            if not match:
                return {}
            
            json_str = match.group(1)
            # Simple repair: balance quotes
            json_str = re.sub(r'"([^"\\]*(?:\\.[^"\\]*)*)"', lambda m: m.group(1), json_str)
            
            try:
                return json.loads(json_str)
            except:
                return {}
        
        result = extract_json(raw)

        # Guarantee non-empty summary
        if not result.get("summary") and email.text.strip():
            # Simple lang detect
            non_ascii_ratio = len([c for c in email.text if ord(c) > 127]) / len(email.text)
            if non_ascii_ratio > 0.3:
                result = {
                    "summary": "Non-English email content detected. English summary unavailable.",
                    "type": "PERS",
                    "priority": "Low",
                    "confidence": 0.3,
                    "flags": {"multilingual": True}
                }
            else:
                # Heuristic fallback
                lines = [l.strip() for l in email.text.split('\n') if l.strip()]
                first_line = lines[0] if lines else "No content"
                subject = email.metadata.get("subject", "No subject")
                urgency_words = ['urgent', 'asap', 'immediate', 'today', 'now']
                priority = "HIGH" if any(word in email.text.lower() for word in urgency_words) else "Normal"
                result = {
                    "summary": f"Subject: {subject}. Priority: {priority}. Content excerpt: {first_line[:200]}...",
                    "type": "BIZ",
                    "category": "Work",
                    "priority": priority,
                    "urgency": "MEDIUM",
                    "confidence": 0.5,
                    "action_items": [],
                    "key_details": {},
                    "flags": {"fallback_used": True}
                }
        elif not email.text.strip():
            result = {
                "summary": "Empty email body provided.",
                "type": "NOTIF",
                "confidence": 0.1
            }

        if result and self._disk_cache and cache_key:
            self._disk_cache.set(cache_key, result)

        return result
