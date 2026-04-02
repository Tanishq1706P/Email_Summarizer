import json
import os
import threading
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pymongo import MongoClient

from logging_utils import setup_logging
from models.data_model import EmailDoc, SummaryResult, UserFeedback
from pipelines.summarizer.config import load_config

logger = setup_logging("learning_store")
CFG = load_config()


class LearningStore:
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

        mongo_cfg = CFG.get("mongodb", {})
        mongo_uri = os.environ.get("MONGO_URI", mongo_cfg.get("uri"))

        # ---------------- MONGO INIT ----------------
        if mongo_uri:
            try:
                self._mongo_client = MongoClient(
                    mongo_uri, serverSelectionTimeoutMS=2000
                )
                self._mongo_client.server_info()

                self._db = self._mongo_client[
                    mongo_cfg.get("db_name", "email_summarizer")
                ]

                self._use_mongo = True

                # ✅ FIX: create index AFTER db init
                self._db.emails.create_index("id", unique=True)

                print(
                    f"LearningStore: MongoDB ({mongo_cfg.get('db_name', 'email_summarizer')})"
                )
                logger.info(
                    "LearningStore initialized with MongoDB",
                    extra={"props": {"db": mongo_cfg.get("db_name")}},
                )

            except Exception as e:
                logger.warning(f"MongoDB unavailable, using JSON fallback: {e}")
                self._use_mongo = False

        else:
            logger.info("No MONGO_URI, using JSON fallback")
            self._use_mongo = False

        # ---------------- JSON FALLBACK ----------------
        if not self._use_mongo:
            self._data = self._load_json()
            print("LearningStore: JSON file")
            logger.info("LearningStore initialized with JSON")

        self._dirty = False
        self._last_save = 0.0

    @property
    def learned_instructions(self) -> str:
        if self._use_mongo:
            try:
                doc = self._db.learned_rules.find_one({"_id": "current"})
                return doc.get("instructions", "") if doc else ""
            except Exception as e:
                logger.warning(f"Failed to fetch learned_instructions: {e}")
                return ""

        return self._data.get("learned_instructions", "")
    # ---------------- JSON STORAGE ----------------
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
            logger.warning(f"_load_json failed: {e}")
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
            logger.error(f"_save_json failed: {e}", exc_info=True)

    def flush(self, force: bool = False) -> None:
        if self._use_mongo:
            return
        with self._lock:
            if not self._dirty and not force:
                return
            self._save_json()

    # ---------------- EMAIL INSERT (DEDUP FIXED) ----------------
    def insert_emails(self, emails: list) -> int:
        from .text_extractor import extract_text

        if not self._use_mongo:
            logger.warning("insert_emails only supported with MongoDB")
            return 0

        try:
            inserted = 0

            for e in emails:
                if not isinstance(e, dict):
                    continue

                raw = e.get("raw") or e.get("text", "")

                # ✅ FIX: hash CLEANED text (not raw)
                clean_text = " ".join(extract_text(raw).split())

                email_id = e.get("id") or hashlib.md5(
                    clean_text.encode()
                ).hexdigest()

                doc = {
                    "id": email_id,
                    "text": clean_text,
                    "metadata": e.get("metadata", {}),
                }

                if "raw" in e:
                    doc["metadata"]["has_raw"] = True

                try:
                    result = self._db.emails.update_one(
                        {"id": email_id},
                        {"$setOnInsert": doc},
                        upsert=True,
                    )

                    if result.upserted_id:
                        inserted += 1

                except Exception as ex:
                    logger.error(f"Insert failed for {email_id}: {ex}")

            logger.info(f"Inserted {inserted} new emails (deduplicated)")
            return inserted

        except Exception as e:
            logger.error(f"insert_emails failed: {e}")
            return 0

    def stats(self) -> Dict[str, Any]:
        if self._use_mongo:
            try:
                total = self._db.feedback.count_documents({})
                return {
                    "total": total,
                    "storage": "mongodb",
                }
            except Exception as e:
                logger.warning(f"Stats failed: {e}")
                return {"total": 0}

        return {
            "total": len(self._data.get("feedback", [])),
            "storage": "json",
        }
    
    # ---------------- FETCH ----------------
    def get_emails(
        self, collection: str = "emails", limit: Optional[int] = None
    ) -> List[EmailDoc]:
        from .text_extractor import extract_text
        import uuid

        if not self._use_mongo:
            logger.warning("get_emails only supported with MongoDB")
            return []

        try:
            query = self._db[collection].find()
            if limit:
                query = query.limit(limit)

            emails = []

            for doc in query:
                try:
                    raw = doc.get("raw") or doc.get("text", "")
                    clean_text = doc.get("text") or extract_text(raw)

                    emails.append(
                        EmailDoc(
                            id=doc.get("id", str(uuid.uuid4())),
                            text=clean_text,
                            user_id=doc.get("user_id", "unknown"),
                            metadata=doc.get("metadata", {}),
                        )
                    )
                except Exception as e:
                    logger.warning(f"Parse failed {doc.get('id')}: {e}")

            return emails

        except Exception as e:
            logger.error(f"Fetch failed: {e}")
            return []

    # ---------------- UPDATE SUMMARY ----------------
    def update_email_summary(
        self, collection: str, email_id: str, summary_result: dict | SummaryResult
    ) -> bool:
        if not self._use_mongo:
            return False

        try:
            data = (
                summary_result
                if isinstance(summary_result, dict)
                else summary_result.model_dump()
            )

            result = self._db[collection].update_one(
                {"id": email_id},
                {"$set": {"summary_result": data}, "$currentDate": {"updated_at": True}},
                upsert=True,
            )

            return result.acknowledged

        except Exception as e:
            logger.error(f"Update failed {email_id}: {e}")
            return False