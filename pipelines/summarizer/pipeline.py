"""
Email Summarization Pipeline (Production Optimized)
Handles core summarization, evaluation, and adaptive learning logic.    
"""

import time
import uuid
import threading
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from models.data_model import (
    EmailDoc, SummaryResult, PipelineMetadata, EvalScores, ActionItem   
)
from pipelines.summarizer.generator import Generator
from pipelines.summarizer.evaluator import Evaluator
from pipelines.summarizer.self_corrector import SelfCorrector
from pipelines.summarizer.adaptive_learning import AdaptiveLearner      
from pipelines.summarizer.store_learning import LearningStore
from pipelines.summarizer.config import load_config
from pipelines.summarizer.embedder import Embedder
from logging_utils import setup_logging

# Setup structured logging
logger = setup_logging("summarizer.pipeline")
CFG = load_config()

class EmailSummarizationPipeline:
    def __init__(self):
        self._training_mode = CFG.get("training_mode", False)
        self._generator     = Generator()
        self._learning_lock = threading.RLock()
        self._store         = LearningStore(CFG.get("learning_store_path"))
        self._learner       = AdaptiveLearner(self._store)
        # Eval/Embed disabled prod (OOM protection)
        self._embedder      = None

        stats = self._store.stats()
        logger.info(
            "Summarizer Pipeline Ready",
            extra={"props": {
                "mode": "TRAINING" if self._training_mode else "INFERENCE",
                "feedback_items": stats.get("total", 0),
                "storage": stats.get("storage", "unknown")
            }}
        )

    def summarize(self, email: EmailDoc) -> SummaryResult:
        # Preprocess for LLM
        email.text = preprocess_email_text(email.text)
        
        """
        Summarize a single pre-masked email.
        """
        t0         = time.perf_counter()
        session_id = str(uuid.uuid4())
        meta       = PipelineMetadata()

        # Inject learned instructions
        learned = self._store.learned_instructions
        meta.learned_rules = len(learned.splitlines()) if learned else 0

        # Generate
        try:
            # The generator now returns a dictionary that we can parse into SummaryResult
            data = self._generator.generate(email, learned_instructions=learned)

            # Evaluate + self-correct (only in training mode)
            data, ev, meta = self._evaluate_and_correct(data, email, learned, meta, t0)

            summary = data.get("summary", "")
            subject = email.metadata.get("subject", "")
            
            # Generate vector embedding for subject and summary
            vector_embedding = None

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
                action_items=[ActionItem(**a) if isinstance(a, dict) else a for a in data.get("action_items", [])],
                open_questions=data.get("open_questions", []),
                deadline=data.get("deadline"),
                priority=data.get("priority", "Normal"),
                urgency=data.get("urgency", "Normal"),
                sentiment=data.get("sentiment", "Neutral"),
                confidence=float(data.get("confidence", 0.0)),
                eval=ev,
                pipeline=meta,
                metadata=data.get("metadata", {})
            )

            logger.info(
                "Summarization successful",
                extra={"props": {
                    "email_id": email.id,
                    "session_id": session_id,
                    "latency_ms": meta.latency_ms,
                    "passed": ev.passed
                }}
            )
            return result

        except Exception as e:
            logger.error("Summarization failed", extra={"props": {"email_id": email.id}}, exc_info=True)
            raise

    def _evaluate_and_correct(
        self,
        data: dict,
        email: EmailDoc,
        learned: str,
        meta: PipelineMetadata,
        t0: float,
    ) -> Tuple[dict, EvalScores, PipelineMetadata]:
        confidence = float(data.get("confidence", 0.0))
        ev = EvalScores()

        if self._training_mode and CFG.get("eval_enabled") and self._evaluator:
            if confidence >= CFG.get("eval_confidence_gate", 0.85):     
                ev.skipped = True
                meta.eval_skipped = True
            else:
                # Evaluator disabled - skip eval block
                pass
                    ActionItem(action=a.get("action", ""))
                    for a in data.get("action_items", [])
                    if isinstance(a, dict)
                ]

                ev = self._evaluator.evaluate(
                    email_text   = email.text,
                    email_emb    = email_emb,
                    summary      = data.get("summary", ""),
                    action_items = action_items_raw,
                    output_json  = data,
                )

                if not ev.passed:
                    max_corrections = CFG.get("eval_max_corrections", 2)
                    best_data = data
                    best_ev = ev

                    for i in range(max_corrections):
                        missing = [iss.replace("Missing:", "").strip() for iss in best_ev.issues if iss.startswith("Missing:")]
                        corrected_data = self._corrector.correct(email, best_data, best_ev, learned_instructions=learned, missing_items=missing)
                        corrected_ev = self._evaluator.evaluate(        
                            email_text   = email.text,
                            email_emb    = email_emb,
                            summary      = corrected_data.get("summary", ""),
                            action_items = action_items_raw,
                            output_json  = corrected_data,
                        )

                        if corrected_ev.overall > best_ev.overall:      
                            best_data = corrected_data
                            best_ev = corrected_ev
                            if best_ev.passed:
                                break

                    data = best_data
                    ev = best_ev
                    meta.correction_count = i + 1

        else:
            ev.skipped = True
            meta.eval_skipped = True

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
