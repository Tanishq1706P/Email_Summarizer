from typing import Optional

from sentence_transformers import SentenceTransformer

from logging_utils import setup_logging
from pipelines.summarizer.config import load_config
import os

# Setup structured logging
logger = setup_logging("summarizer.embedder")
CFG = load_config()


class Embedder:
    """
    Embedder for production use - loads sentence-transformers model.
    Ensure sufficient RAM (>4GB available).
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        self.model_name = model_name or CFG.get(
            "eval_model", "sentence-transformers/all-MiniLM-L6-v2"
        )
        self._model = None

        if os.environ.get("RENDER") == "true":
            logger.info("Embedder disabled for Render free tier (RAM)")
            return

        try:
            self._model = SentenceTransformer(self.model_name)
            logger.info(f"Embedder initialized with model: {self.model_name}")
        except Exception as e:
            logger.error(
                f"Failed to load embedding model '{self.model_name}': {e}",
                exc_info=True,
            )
            self._model = None

    def get_embedding(self, text: str) -> str:
        if not text or not self._model:
            return ""
        try:
            embedding = self._model.encode(text)
            return str(embedding.tolist())
        except Exception as e:
            logger.error(f"Error generating embedding: {e}", exc_info=True)
            return ""

    def embed_summary_and_subject(self, summary: str, subject: str) -> str:
        combined_text = f"Subject: {subject}\nSummary: {summary}"
        return self.get_embedding(combined_text)
