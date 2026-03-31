from abc import ABC, abstractmethod
from typing import List
from models.job import Job
from models.search_config import SearchConfig


class BaseScraper(ABC):
    """Abstract base class for all job scrapers."""

    SOURCE_NAME: str = ""

    def __init__(self, config: SearchConfig):
        self.config = config

    @abstractmethod
    def fetch_jobs(self) -> List[Job]:
        """Fetch and return a list of Job objects."""
        raise NotImplementedError

    def _safe_strip(self, value, default: str = "") -> str:
        if value is None:
            return default
        return str(value).strip()
