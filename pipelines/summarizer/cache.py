import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


@dataclass
class DiskCache:
    """
    Very small, dependency-free on-disk cache.
    Stores one JSON file per key: <cache_dir>/<prefix>/<key>.json
    """

    cache_dir: Path
    ttl_seconds: int = 24 * 3600
    max_entries: int = 5000

    def __post_init__(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def make_key(self, *, namespace: str, model: str, system: str, user: str) -> str:
        # Avoid huge keys; hash inputs.
        content = json.dumps(
            {
                "ns": namespace,
                "model": model,
                "system": system,
                "user": user,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return _sha256(content)

    def _path_for(self, key: str) -> Path:
        return self.cache_dir / key[:2] / f"{key}.json"

    def get(self, key: str) -> Any | None:
        p = self._path_for(key)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            ts = float(data.get("_ts", 0))
            if self.ttl_seconds > 0 and (time.time() - ts) > self.ttl_seconds:
                try:
                    p.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning("DiskCache cleanup unlink failed for %s: %s", p, e)
                return None
            return data.get("value")
        except Exception as e:
            logger.warning("DiskCache get() failed for %s: %s", p, e)
            return None

    def set(self, key: str, value: Any) -> None:
        p = self._path_for(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"_ts": time.time(), "value": value}
        try:
            p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning("DiskCache set() failed for %s: %s", p, e)
            return
        self._evict_if_needed()

    def _evict_if_needed(self) -> None:
        if self.max_entries <= 0:
            return
        # Best-effort eviction: if we exceed max_entries, remove oldest files.
        try:
            files = list(self.cache_dir.glob("*/*.json"))
            if len(files) <= self.max_entries:
                return
            files.sort(key=lambda fp: fp.stat().st_mtime)
            for fp in files[: max(0, len(files) - self.max_entries)]:
                try:
                    fp.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning("DiskCache unlink failed for %s: %s", fp, e)
        except Exception as e:
            logger.warning("DiskCache eviction failed: %s", e)

