import json
import os
import tempfile
import threading
import time
from hashlib import sha1
from typing import Any, Optional


class LLMCache:
    """
    Tiny JSON-file cache for LLM results to avoid re-analyzing the same job
    across reruns (Streamlit reruns, repeated searches, etc.).
    """

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not os.path.exists(self.path):
            self._data = {}
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f) or {}
        except Exception:
            self._data = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        # Windows can raise PermissionError if another process/scan briefly holds the file.
        # Use a unique temp file + retry atomic replace.
        dir_ = os.path.dirname(self.path) or "."
        last_exc: Exception | None = None
        for attempt in range(6):
            fd, tmp = tempfile.mkstemp(prefix="llm_cache_", suffix=".json.tmp", dir=dir_)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False)
                try:
                    os.replace(tmp, self.path)
                    return
                except PermissionError as e:
                    last_exc = e
                    time.sleep(0.05 * (attempt + 1))
            finally:
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    pass
        if last_exc:
            raise last_exc

    @staticmethod
    def make_key(model: str, job_id: str, apply_url: str, description: str) -> str:
        h = sha1((apply_url + "\n" + (description or "")).encode("utf-8", errors="ignore")).hexdigest()[:16]
        return f"{model}::{job_id}::{h}"

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            self._load()
            return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._load()
            self._data[key] = value
            self._save()

