"""
Email Summarization Pipeline
Handles summarization and feedback collection.
"""

from typing import Dict, Any
import time
import threading
from models.data_model import EmailDoc, UserFeedback
from pipelines.summarizer.pipeline import EmailSummarizationPipeline as SummarizerPipeline
from pipelines.summarizer.config import load_config
from pipelines.summarizer.store_learning import LearningStore
from logging_utils import setup_logging
from circuit_breaker import CircuitBreaker

# Setup structured logging
logger = setup_logging("pipeline")

# ARC-5: Global circuit breaker for LLM services
llm_circuit = CircuitBreaker("ollama_llm", failure_threshold=3, recovery_timeout_seconds=60)


class EmailSummarizationPipeline:
    def __init__(self):
        self._cfg = load_config()
        # Preprocess email before pipeline
        email.text = preprocess_email_text(email.text)
        self._delegate = SummarizerPipeline()
        self._store = LearningStore(self._cfg.get("learning_store_path"))
        self._learning_lock = threading.RLock()
        logger.info("Pipeline initialized", extra={"props": {"learning_enabled": self._cfg.get("learning_enabled")}} )

    def summarize(self, email: EmailDoc) -> Dict[str, Any]:
        """Normalize results from summarizer pipeline and persist session state."""
        start_time = time.perf_counter()
        
        try:
            # ARC-5: Wrap delegate call in Circuit Breaker
            # No more internal model conversion needed as they share the same model
            result = llm_circuit.call(self._delegate.summarize, email)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Keep a lightweight session store for feedback correlation
            if self._cfg.get("learning_enabled"):
                with self._learning_lock:
                    try:
                        self._store.record_session(result.session_id, email, result)
                        if not self._cfg.get("learning_immediate_save", False):
                            self._store.flush()
                    except Exception as e:
                        logger.warning("Failed to record session in learning store", exc_info=True)

            logger.info(
                "Summarization complete",
                extra={"props": {
                    "email_id": email.id,
                    "session_id": result.session_id,
                    "duration_ms": duration_ms,
                    "confidence": result.confidence
                }}
            )
            # result is already a Pydantic model
            return result.model_dump()
            
        except Exception as e:
            logger.error("Pipeline summarization failed", extra={"props": {"email_id": email.id}}, exc_info=True)
            raise

    def feedback(self, feedback: UserFeedback):
        """Record user feedback; optionally run consolidation."""
        start_time = time.perf_counter()
        
        try:
            self._delegate.feedback(feedback)

            if self._cfg.get("learning_enabled"):
                with self._learning_lock:
                    try:
                        self._store.record_feedback(feedback)
                        if not self._cfg.get("learning_immediate_save", False):
                            self._store.flush()
                    except Exception as e:
                        logger.warning("Failed to record feedback in learning store", exc_info=True)

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Feedback recorded",
                extra={"props": {
                    "session_id": feedback.session_id,
                    "rating": feedback.rating,
                    "duration_ms": duration_ms
                }}
            )
            
            return {"status": "received", "session_id": feedback.session_id}
            
        except Exception as e:
            logger.error("Feedback processing failed", extra={"props": {"session_id": feedback.session_id}}, exc_info=True)
            raise
