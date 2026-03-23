import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent

def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst

def default_config() -> dict[str, Any]:
    """
    Production-optimized defaults for local inference with Ollama.
    """
    return {
        # ---- Runtime ----
        "offline": False,
        "ollama_host": os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        "ollama_timeout_seconds": 120,
        "ollama_keep_alive": "10m",
        "ollama_num_retries": 2,
        "ollama_retry_backoff_seconds": 0.5,

        # ---- Model settings ----
        "llm": os.environ.get("LLM_MODEL", "qwen2.5:1.5b"),
        "temperature": 0.1,
        "num_predict": 512,
        "num_ctx": 4096,

        # ---- Input trimming ----
        "max_body_chars": 8000,
        "body_tail_chars": 1200,

        # ---- Paths ----
        "prompt_path": str(_BASE_DIR / "prompts" / "summarization_prompt.txt"),
        "learning_store_path": str(_BASE_DIR / "learning_store.json"),
        "cache_dir": str(_BASE_DIR / ".cache"),

        # ---- Adaptive Learning (Production: Passive) ----
        "training_mode": False,  # Set to True only for specialized learning phases
        "learning_enabled": True,
        "consolidation_every_n": 50,  # Less frequent in production
        "min_feedback_to_learn": 20,

        # ---- Evaluation (Production: Disabled by default) ----
        "eval_enabled": False, 
        "eval_confidence_gate": 0.85,
        "eval_max_corrections": 1, # Minimal corrections in production
        "eval_model": "sentence-transformers/all-MiniLM-L6-v2",
        "eval_weights": {"answer_relevance": 0.4, "faithfulness": 0.4, "context_richness": 0.2},

        # ---- Caching ----
        "cache_enabled": True,
        "cache_ttl_seconds": 3600 * 24, # 24 hours
        "cache_max_entries": 10000,

        # ---- Concurrency ----
        "default_max_workers": 4,

        # ---- MongoDB ----
        "mongodb": {
            "uri": os.environ.get("MONGO_URI", "mongodb://localhost:27017"),
            "db_name": os.environ.get("MONGO_DB", "email_summarizer"),
            "emails_collection": "emails",
            "summaries_collection": "summaries"
        },
    }

def load_config() -> dict[str, Any]:
    cfg = default_config()
    
    # Load from file if present
    cfg_path = os.environ.get("SUMMARIZER_CONFIG")
    path = Path(cfg_path) if cfg_path else (_BASE_DIR / "config.json")
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _deep_merge(cfg, data)
        except Exception as e:
            logger.error("Failed to load config file %s: %s", path, e)

    # Apply general JSON override if present
    override_json = os.environ.get("SUMMARIZER_CONFIG_OVERRIDE")
    if override_json:
        try:
            override_data = json.loads(override_json)
            if isinstance(override_data, dict):
                _deep_merge(cfg, override_data)
        except Exception as e:
            logger.warning("Failed to parse SUMMARIZER_CONFIG_OVERRIDE: %s", e)

    # Resolve paths relative to summarizer dir
    for path_key in ["prompt_path", "learning_store_path", "cache_dir"]:
        try:
            p = Path(cfg.get(path_key, ""))
            if p and not p.is_absolute():
                cfg[path_key] = str((_BASE_DIR / p).resolve())
        except Exception as e:
            logger.warning("Failed to resolve %s: %s", path_key, e)

    return cfg
