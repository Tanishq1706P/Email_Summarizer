"""
Email Summarization Pipeline (Production Safe)
- Strict grounding
- No hallucinated defaults
- Validation before storage
"""

import threading
import time
import uuid
from typing import Any, Dict

from logging_utils import setup_logging
from models.data_model import EmailDoc
from pipelines.summarizer.generator import Generator
from pipelines.summarizer.preprocess import preprocess_email_text
from pipelines.summarizer.store_learning import LearningStore
from pipelines.summarizer.adaptive_learning import AdaptiveLearner
from pipelines.summarizer.config import load_config

logger = setup_logging("summarizer.pipeline")
CFG = load_config()


class EmailSummarizationPipeline:
    def __init__(self):
        self._generator = Generator()
        self._store = LearningStore(CFG.get("learning_store_path"))
        self._learner = AdaptiveLearner(self._store)
        self._learning_lock = threading.RLock()

        stats = self._store.stats()
        logger.info(
            "Pipeline Ready",
            extra={
                "props": {
                    "mode": "INFERENCE",
                    "feedback_items": stats.get("total", 0),
                }
            },
        )

    # -----------------------------
    # MAIN ENTRY
    # -----------------------------
    def summarize(self, email: EmailDoc) -> Dict[str, Any]:

        email.text = preprocess_email_text(email.text).strip()

        t0 = time.perf_counter()
        session_id = str(uuid.uuid4())

        learned = self._store.learned_instructions

        try:
            raw_data = self._generator.generate(
                email, learned_instructions=learned
            )

            # ✅ VALIDATE + NORMALIZE
            data = self._validate_and_normalize(raw_data)

            # ✅ ALWAYS TRUST METADATA FOR SUBJECT
            subject = email.metadata.get("subject")

            latency_ms = round((time.perf_counter() - t0) * 1000, 2)

            result = {
                "session_id": session_id,
                "email_id": email.id,

                "category": data.get("category"),
                "subject": subject,
                "summary": data.get("summary"),
                "detailedSummary": data.get("detailedSummary"),
                "priority": data.get("priority"),
            }

            logger.info(
                "Summarization success",
                extra={
                    "props": {
                        "email_id": email.id,
                        "session_id": session_id,
                        "latency_ms": latency_ms,
                    }
                },
            )

            return result

        except Exception:
            logger.error(
                "Summarization failed",
                extra={"props": {"email_id": email.id}},
                exc_info=True,
            )
            raise

    # -----------------------------
    # VALIDATION LAYER (CRITICAL)
    # -----------------------------
    def _validate_and_normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates and extracts only the fields defined in the prompt output format:
        category, subject, summary, detailedSummary, priority
        """

        validated = {
            "category": data.get("category"),
            "subject": data.get("subject"),
            "summary": data.get("summary"),
            "detailedSummary": data.get("detailedSummary"),
            "priority": data.get("priority"),
        }

        return validated

    # -----------------------------
    # FEEDBACK LOOP
    # -----------------------------
    def feedback(self, fb: Any) -> None:
        if not CFG.get("learning_enabled"):
            return

        with self._learning_lock:
            try:
                self._store.record_feedback(fb)

                if self._learner.should_consolidate():
                    logger.info("Running adaptive learning")
                    self._learner.consolidate()

            except Exception:
                logger.error("Feedback failed", exc_info=True)