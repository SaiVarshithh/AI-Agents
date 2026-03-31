from abc import ABC, abstractmethod
from models.job import Job
from models.search_config import SearchConfig


class BaseLLM(ABC):
    """Abstract base for LLM scoring and analysis providers."""

    def __init__(self, config: SearchConfig):
        self.config = config

    @abstractmethod
    def score_job(self, job: Job) -> tuple[float, str]:
        """
        Returns (relevance_score: 0-100, match_summary: str).
        """
        raise NotImplementedError

    @abstractmethod
    def analyze_job_detailed(self, job: Job) -> dict:
        """
        Returns dict with keys: relevance_score, tech_stack,
        joining_period, location_detail, detailed_summary.
        """
        raise NotImplementedError