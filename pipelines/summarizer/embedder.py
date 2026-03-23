import logging
import threading
from typing import List, Union, Optional
from sentence_transformers import SentenceTransformer
from pipelines.summarizer.config import load_config
from logging_utils import setup_logging

# Setup structured logging
logger = setup_logging("summarizer.embedder")
CFG = load_config()

class Embedder:
    """
    Handles vector embedding generation for email components.
    Uses singleton pattern to share the model across components.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Embedder, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, model_name: Optional[str] = None) -> None:
        if self._initialized:
            return
        
        self.model_name = model_name or CFG.get("embedding_model", "all-MiniLM-L6-v2")
        self._model = None
        self._load_model()
        self._initialized = True

    def _load_model(self):
        try:
            # SentenceTransformer handles caching internally
            self._model = SentenceTransformer(self.model_name)
            logger.info(f"Embedder initialized with model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load embedding model '{self.model_name}': {e}", exc_info=True)
            # We don't want to crash the whole pipeline if embedding fails
            self._model = None

    def get_embedding(self, text: str) -> str:
        """Generates embedding and returns it as a string representation."""
        if not text or not self._model:
            return ""
        
        try:
            embedding = self._model.encode(text)
            # Returning as string as per user requirement
            return str(embedding.tolist())
        except Exception as e:
            logger.error(f"Error generating embedding for text: {e}", exc_info=True)
            return ""

    def embed_summary_and_subject(self, summary: str, subject: str) -> str:
        """Combines subject and summary into a single embedding string."""
        combined_text = f"Subject: {subject}\nSummary: {summary}"
        return self.get_embedding(combined_text)
