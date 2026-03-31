from __future__ import annotations

import json
import os
from typing import Iterable

from config.settings import settings
from models.job import Job


class AppliedStore:
    """
    Tiny persistence layer for applied status.

    Stored as JSON so it's simple and portable.
    """

    def __init__(self, filepath: str | None = None):
        self.filepath = filepath or os.path.join(settings.OUTPUT_DIR, "applied.json")
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)

    def load(self) -> dict[str, bool]:
        if not os.path.exists(self.filepath):
            return {}
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                return {str(k): bool(v) for k, v in raw.items()}
        except Exception:
            return {}
        return {}

    def save(self, data: dict[str, bool]) -> None:
        tmp = f"{self.filepath}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, self.filepath)

    def key_for_job(self, job: Job) -> str:
        # Prefer stable external URL; fallback to source+job_id.
        if job.apply_url:
            return f"url::{job.apply_url}"
        if job.source and job.job_id:
            return f"id::{job.source}::{job.job_id}"
        return f"fallback::{job.source}::{job.title}::{job.company}"

    def apply_to_jobs(self, jobs: Iterable[Job]) -> None:
        data = self.load()
        for j in jobs:
            j.applied = bool(data.get(self.key_for_job(j), False))

    def update_from_jobs(self, jobs: Iterable[Job]) -> None:
        data = self.load()
        for j in jobs:
            data[self.key_for_job(j)] = bool(j.applied)
        self.save(data)

