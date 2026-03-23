import json
from typing import List, Dict, Any
from models.data_model import UserFeedback
from pipelines.summarizer.store_learning import LearningStore
from pipelines.summarizer.config import load_config
from pipelines.summarizer.ollama_local import LocalOllama, OllamaSettings
from logging_utils import setup_logging

# Setup structured logging
logger = setup_logging("summarizer.learner")
CFG = load_config()

class AdaptiveLearner:
    """
    Consolidates feedback into learned rules.
    """
    def __init__(self, store: LearningStore) -> None:
        self._store = store
        self._llm = LocalOllama(
            OllamaSettings(
                host=str(CFG.get("ollama_host", "http://127.0.0.1:11434")),
                offline=True
            )
        )

    def should_consolidate(self) -> bool:
        n = CFG.get("consolidation_every_n", 50)
        total = self._store.total_feedback
        done = self._store.consolidation_count
        return total >= (done + 1) * n

    def consolidate(self) -> str:
        """Runs the consolidation pass."""
        logger.info("Consolidating feedback into learned rules")
        # Logic to generate learned_instructions string
        return self._store.learned_instructions
