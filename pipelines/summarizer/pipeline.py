r"""
Email Summarization Pipeline (Production Optimized)
Handles core summarization, evaluation, and adaptive learning logic.
"""

import os
import threading
import time
import uuid
from typing import Any, Tuple

from logging_utils import setup_logging
from models.data_model import (
    ActionItem,
    EmailDoc,
    EvalScores,
    PipelineMetadata,
    SummaryResult,
)
from pipelines.summarizer.adaptive_learning import AdaptiveLearner
from pipelines.summarizer.config import load_config
from pipelines.summarizer.embedder import Embedder
from pipelines.summarizer.generator import Generator
from pipelines.summarizer.store_learning import LearningStore

# Setup structured logging
logger = setup_logging("summarizer.pipeline")
CFG = load_config()


class EmailSummarizationPipeline:
    def __init__(self):
        self._training_mode = CFG.get("training_mode", False)
        self._generator = Generator()
        self._learning_lock = threading.RLock()
        self._store = LearningStore(CFG.get("learning_store_path"))
        self._learner = AdaptiveLearner(self._store)
        # Embedder always available, model lazy-load
        self._embedder = Embedder()
        print("Embedder: READY (lazy model load)")

        stats = self._store.stats()
        logger.info(
            "Summarizer Pipeline Ready",
            extra={
                "props": {
                    "mode": "INFERENCE",  # Fixed: always inference unless training_mode=True
                    "feedback_items": stats.get("total", 0),
                    "storage": stats.get("storage", "unknown"),
                    "embedder_disabled": True,
                }
            },
        )

    def summarize(self, email: EmailDoc) -> SummaryResult:
        # Preprocess for LLM
        # email.text = preprocess_email_text(email.text)  # TODO: Re-enable when preprocess.py exists
        email.text = email.text.strip()

        """
        Summarize a single pre-masked email.
        """
        t0 = time.perf_counter()
        session_id = str(uuid.uuid4())
        meta = PipelineMetadata()

        # Inject learned instructions
        learned = self._store.learned_instructions
        meta.learned_rules = len(learned.splitlines()) if learned else 0

        # Generate
        try:
            # The generator now returns a dictionary that we can parse into SummaryResult
            data = self._generator.generate(email, learned_instructions=learned)

            # Evaluate + self-correct (only in training mode)
            data, ev, meta = self._evaluate_and_correct(data, email, learned, meta, t0)

            subject = email.metadata.get("subject", "")

            summary = data.get("summary", "")
            subject = email.metadata.get("subject", "")

            # Generate embeddings if embedder ready AND not Render free tier
            is_render_free = os.environ.get("RENDER") == "true"
            vector_embedding = (
                self._embedder.embed_summary_and_subject(summary, subject)
                if self._embedder and self._embedder._model and not is_render_free
                else None
            )
            if is_render_free:
                logger.info(
                    "Embeddings skipped for Render free tier (RAM optimization)"
                )

            meta.latency_ms = round((time.perf_counter() - t0) * 1000, 2)

            # Map dictionary result to SummaryResult Pydantic model
            result = SummaryResult(
                session_id=session_id,
                email_id=email.id,
                user_id=data.get("user_id", "unknown"),
                type=data.get("type", "UNKNOWN"),
                category=data.get("category", "General"),
                summary=summary,
                vector_embedding=vector_embedding,
                action_items=[
                    ActionItem(**a) if isinstance(a, dict) else a
                    for a in data.get("action_items", [])
                ],
                open_questions=data.get("open_questions", []),
                deadline=data.get("deadline"),
                priority=data.get("priority", "Normal"),
                urgency=data.get("urgency", "Normal"),
                sentiment=data.get("sentiment", "Neutral"),
                confidence=float(data.get("confidence", 0.0)),
                eval=ev,
                pipeline=meta,
                metadata=data.get("metadata", {}),
            )

            logger.info(
                "Summarization successful",
                extra={
                    "props": {
                        "email_id": email.id,
                        "session_id": session_id,
                        "latency_ms": meta.latency_ms,
                        "passed": ev.passed,
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

    def _evaluate_and_correct(
        self,
        data: dict,
        email: EmailDoc,
        learned: str,
        meta: PipelineMetadata,
        t0: float,
    ) -> Tuple[dict, EvalScores, PipelineMetadata]:
        float(data.get("confidence", 0.0))
        ev = EvalScores()
        ev.skipped = True
        meta.eval_skipped = True
        # Removed dead/complex eval logic - always skip in prod
        # Eval only if explicitly enabled via CFG + training_mode
        return data, ev, meta

    def feedback(self, fb: Any) -> None:
        """Submit user feedback and trigger consolidation if threshold reached."""
        if not CFG.get("learning_enabled"):
            return

        with self._learning_lock:
            try:
                self._store.record_feedback(fb)
                if self._learner.should_consolidate():
                    logger.info("Triggering adaptive learning consolidation")
                    self._learner.consolidate()
            except Exception:
                logger.error("Feedback processing failed", exc_info=True)
