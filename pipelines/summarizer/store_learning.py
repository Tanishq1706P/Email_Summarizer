import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pymongo import MongoClient

# from pipelines.summarizer.embedder import Embedder  # Disabled prod
from logging_utils import setup_logging
from models.data_model import EmailDoc, SummaryResult, UserFeedback
from pipelines.summarizer.config import load_config

# Setup structured logging
logger = setup_logging("learning_store")
CFG = load_config()


class LearningStore:
    """
    Centralized store for sessions, feedback, and learned rules.
    Supports MongoDB for production (multi-worker consistency) and JSON for local/dev.
    """

    _EMPTY = {
        "sessions": {},
        "feedback": [],
        "learned_instructions": "",
        "consolidation_count": 0,
        "total_feedback": 0,
    }

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = Path(path) if path else None
        self._lock = threading.RLock()
        self._mongo_client: Optional[MongoClient] = None
        self._db = None
        self._use_mongo = False
        # Embedder disabled prod OOM - fixed in pipeline.py

        # Initialize MongoDB if URI is provided
        mongo_cfg = CFG.get("mongodb", {})
        mongo_uri = os.environ.get("MONGO_URI", mongo_cfg.get("uri"))

        if mongo_uri:
            try:
                self._mongo_client = MongoClient(
                    mongo_uri, serverSelectionTimeoutMS=2000
                )
                # Test connection
                self._mongo_client.server_info()
                self._db = self._mongo_client[
                    mongo_cfg.get("db_name", "email_summarizer")
                ]
                self._use_mongo = True
                print(
                    f"LearningStore: MongoDB ({mongo_cfg.get('db_name', 'email_summarizer')})"
                )
                logger.info(
                    "LearningStore initialized with MongoDB",
                    extra={
                        "props": {"db": mongo_cfg.get("db_name", "email_summarizer")}
                    },
                )
            except Exception as e:
                logger.warning(
                    f"MongoDB unavailable, using JSON fallback: {e}"
                )
                self._use_mongo = False
        else:
            logger.info("No MONGO_URI, using JSON fallback")
            self._use_mongo = False

        if not self._use_mongo:
            self._data = self._load_json()
            print("LearningStore: JSON file")
            logger.info("LearningStore initialized with JSON")

        self._dirty = False
        self._last_save = 0.0

    def _load_json(self) -> Dict[str, Any]:
        data = {
            k: v.copy() if isinstance(v, dict) else v for k, v in self._EMPTY.items()
        }
        if not self._path or not self._path.exists():
            return data
        try:
            with self._lock:
                loaded = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except Exception as e:
            logger.warning(f"LearningStore _load_json failed: {e}")
        return data

    def _save_json(self) -> None:
        if not self._path:
            return
        try:
            self._path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._dirty = False
            self._last_save = time.time()
        except Exception as e:
            logger.error(f"LearningStore _save_json failed: {e}", exc_info=True)

    def flush(self, force: bool = False) -> None:
        """Persist data when needed or forcefully."""
        if self._use_mongo:
            return  # MongoDB updates are immediate

        with self._lock:
            if not self._dirty and not force:
                return
            self._save_json()

    def record_session(
        self, session_id: str, email: EmailDoc, result: SummaryResult
    ) -> None:
        subject = email.metadata.get("subject", "")
        summary = result.summary

        # Use embedding from pipeline result
        vector_embedding = result.vector_embedding

        session_data = {
            "session_id": session_id,
            "email_id": email.id,
            "email_type": result.type,
            "subject": subject,
            "summary": summary,
            "vector_embedding": vector_embedding,
            "priority": result.priority,
            "urgency": result.urgency,
            "sentiment": result.sentiment,
            "confidence": result.confidence,
            "eval": {
                "answer_relevance": result.eval.answer_relevance,
                "faithfulness": result.eval.faithfulness,
                "overall": result.eval.overall,
                "passed": result.eval.passed,
                "issues": result.eval.issues,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if self._use_mongo:
            self._db.sessions.update_one(
                {"session_id": session_id}, {"$set": session_data}, upsert=True
            )
        else:
            with self._lock:
                self._data["sessions"][session_id] = session_data
                self._dirty = True
                self._check_auto_save()

    def record_feedback(self, fb: UserFeedback) -> None:
        # Fetch session for context
        session = {}
        if self._use_mongo:
            session = self._db.sessions.find_one({"session_id": fb.session_id}) or {}
        else:
            session = self._data["sessions"].get(fb.session_id, {})

        record = {
            "session_id": fb.session_id,
            "email_type": session.get("email_type", "UNKNOWN"),
            "rating": fb.rating,
            "correction": fb.correction,
            "missing_items": fb.missing_items,
            "tone_off": fb.tone_off,
            "wrong_priority": fb.wrong_priority,
            "wrong_type": fb.wrong_type,
            "note": fb.note,
            "original_summary": session.get("summary", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if self._use_mongo:
            self._db.feedback.insert_one(record)
            self._db.stats.update_one(
                {"_id": "global"}, {"$inc": {"total_feedback": 1}}, upsert=True
            )
        else:
            with self._lock:
                self._data["feedback"].append(record)
                self._data["total_feedback"] += 1
                self._dirty = True
                self._check_auto_save()

    @property
    def learned_instructions(self) -> str:
        if self._use_mongo:
            doc = self._db.learned_rules.find_one({"_id": "current"})
            return doc.get("instructions", "") if doc else ""
        return self._data.get("learned_instructions", "")

    def update_learned_instructions(self, instructions: str) -> None:
        if self._use_mongo:
            self._db.learned_rules.update_one(
                {"_id": "current"},
                {
                    "$set": {
                        "instructions": instructions,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
            self._db.stats.update_one(
                {"_id": "global"}, {"$inc": {"consolidation_count": 1}}, upsert=True
            )
        else:
            with self._lock:
                self._data["learned_instructions"] = instructions
                self._data["consolidation_count"] += 1
                self._dirty = True
                self._check_auto_save()

    def _check_auto_save(self) -> None:
        interval = int(CFG.get("learning_save_interval_seconds", 10))
        if CFG.get("learning_immediate_save", False) or (
            time.time() - self._last_save >= interval
        ):
            self._save_json()

    @property
    def total_feedback(self) -> int:
        if self._use_mongo:
            doc = self._db.stats.find_one({"_id": "global"})
            return doc.get("total_feedback", 0) if doc else 0
        return self._data["total_feedback"]

    @property
    def consolidation_count(self) -> int:
        if self._use_mongo:
            doc = self._db.stats.find_one({"_id": "global"})
            return doc.get("consolidation_count", 0) if doc else 0
        return self._data["consolidation_count"]

    def recent_feedback(self, n: int = 20) -> List[Dict[str, Any]]:
        if self._use_mongo:
            return list(self._db.feedback.find().sort("timestamp", -1).limit(n))
        return self._data["feedback"][-n:]

    def low_rated_feedback(self, threshold: int = 3) -> List[Dict[str, Any]]:
        if self._use_mongo:
            return list(self._db.feedback.find({"rating": {"$lte": threshold}}))
        return [f for f in self._data["feedback"] if f["rating"] <= threshold]

    def stats(self) -> Dict[str, Any]:
        if self._use_mongo:
            total = self.total_feedback
            if total == 0:
                return {
                    "total": 0,
                    "avg_rating": 0.0,
                    "consolidations": self.consolidation_count,
                }

            # Simple aggregation for average rating
            pipeline = [{"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}}}]
            agg = list(self._db.feedback.aggregate(pipeline))
            avg_rating = round(agg[0]["avg_rating"], 2) if agg else 0.0

            low_rated = self._db.feedback.count_documents({"rating": {"$lte": 2}})

            return {
                "total": total,
                "avg_rating": avg_rating,
                "low_rated": low_rated,
                "consolidations": self.consolidation_count,
                "learned_rules": len(self.learned_instructions.splitlines()),
                "storage": "mongodb",
            }

        fb = self._data["feedback"]
        if not fb:
            return {
                "total": 0,
                "avg_rating": 0.0,
                "consolidations": 0,
                "storage": "json",
            }
        return {
            "total": len(fb),
            "avg_rating": round(sum(f["rating"] for f in fb) / len(fb), 2),
            "low_rated": sum(1 for f in fb if f["rating"] <= 2),
            "consolidations": self._data["consolidation_count"],
            "learned_rules": len(self.learned_instructions.splitlines()),
            "storage": "json",
        }

    def update_email_summary(
        self, collection: str, email_id: str, summary_result: dict | SummaryResult
    ) -> bool:
        """Update email document with summary_result."""
        if not self._use_mongo:
            logger.warning("update_email_summary only supported with MongoDB")
            return False

        try:
            if isinstance(summary_result, dict):
                summary_data = summary_result
            else:
                summary_data = summary_result.model_dump()
            update_data = {"summary_result": summary_data}
            result = self._db[collection].update_one(
                {"id": email_id},
                {"$set": update_data, "$currentDate": {"updated_at": True}},
                upsert=True,
            )
            success = result.acknowledged and (result.modified_count > 0 or result.upserted_id is not None)
            logger.info(
                f"Updated email {email_id}: modified={result.modified_count}, upserted={'yes' if result.upserted_id else 'no'}, success={success}"
            )
            return success
        except Exception as e:
            logger.error(f"Failed to update email {email_id}: {e}")
            return False

    def insert_emails(self, emails: list) -> int:
        """Insert emails into 'emails' collection. Extract text from raw MIME."""
        from .text_extractor import extract_text
        if not self._use_mongo:
            logger.warning("insert_emails only supported with MongoDB")
            return 0

        try:
            processed = []
            for e in emails:
                if not isinstance(e, dict):
                    continue
                e["id"] = e.get("id") or str(uuid.uuid4())
                raw = e.get("raw") or e.get("text", "")
                e["text"] = extract_text(raw)
                e.setdefault("metadata", {})
                if "raw" in e:
                    e["metadata"]["has_raw"] = True
                processed.append(e)
            
            result = self._db.emails.insert_many(processed)
            logger.info(f"Inserted {len(result.inserted_ids)} emails with extracted text")
            return len(result.inserted_ids)
        except Exception as e:
            logger.error(f"Failed to insert emails: {e}")
            return 0

    def get_emails(
        self, collection: str = "emails", limit: Optional[int] = None
    ) -> List[EmailDoc]:
        """Fetch emails from specified collection for batch processing."""
        from .text_extractor import extract_text
        if not self._use_mongo:
            logger.warning("get_emails only supported with MongoDB")
            return []

        try:
            query = self._db[collection].find()
            if limit:
                query = query.limit(limit)

            emails = []
            import uuid

            for doc in query:
                try:
                    # Prefer existing text, fallback to extract from raw
                    raw_content = doc.get('raw') or doc.get('text', '')
                    clean_text = doc.get('text') or extract_text(raw_content)
                    
                    email_doc = EmailDoc(
                        id=doc.get("id", str(uuid.uuid4())),
                        text=clean_text,
                        user_id=doc.get("user_id", "unknown"),
                        metadata=doc.get("metadata", {}),
                    )
                    emails.append(email_doc)
                    logger.debug(f"Email {email_doc.id}: text_len={len(clean_text)}")
                except Exception as e:
                    logger.warning(f"Failed to parse email {doc.get('id')}: {e}")

            logger.info(f"Fetched {len(emails)} emails from {collection}")
            return emails
        except Exception as e:
            logger.error(f"Failed to fetch emails from {collection}: {e}")
            return []

