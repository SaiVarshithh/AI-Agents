from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchConfig:
    """All configurable search parameters — every field is optional."""

    # Core search
    keywords: str = ""                        # e.g. "Python Developer, FastAPI"
    locations: list = field(default_factory=list)  # e.g. ["Hyderabad", "Bangalore"]

    # Experience filter
    experience_min: Optional[int] = None      # in years
    experience_max: Optional[int] = None

    # Salary / CTC filter
    ctc_min: Optional[float] = None           # in LPA
    ctc_max: Optional[float] = None

    # Tech stack filter (used for LLM relevance scoring)
    tech_stacks: list = field(default_factory=list)  # e.g. ["FastAPI", "PostgreSQL"]

    # Job posting age
    job_age_days: int = 7                     # posted within last N days

    # Result limits
    max_results_total: int = 50               # overall cap across all sources
    max_results_per_source: int = 25          # cap per source (each source may have API limits)

    # Which job portals to scrape (configurable)
    sources: list = field(default_factory=lambda: ["naukri", "monster"])

    # Optional filters
    job_type: Optional[str] = None            # "full_time", "part_time", "contract"
    industry: Optional[str] = None
    desired_role: str = ""                    # free-text for LLM context
    total_experience: Optional[int] = None    # user's own experience (for LLM context)
    candidate_resume_text: str = ""           # extracted from uploaded PDF/DOCX

    # LLM settings
    hf_token: str = ""
    hf_model: str = "mistralai/Mistral-7B-Instruct-v0.3"
    enable_llm_scoring: bool = True
    llm_score_threshold: float = 0.0         # filter out jobs below this score

    # Browser automation (for protected sites)
    playwright_enabled: bool = True
    playwright_headless: bool = True
    playwright_storage_state_path: str = ""  # path to Playwright storage_state JSON (cookies/session)

    def __post_init__(self):
        """Normalize and coerce field types after init."""
        # Ensure list fields are actually lists (not None or strings from JSON deserialization)
        if not isinstance(self.locations, list):
            self.locations = list(self.locations) if self.locations else []
        if not isinstance(self.tech_stacks, list):
            self.tech_stacks = list(self.tech_stacks) if self.tech_stacks else []
        if not isinstance(self.sources, list):
            self.sources = list(self.sources) if self.sources else ["naukri", "monster"]

        # Coerce numeric fields
        if self.job_age_days is not None:
            self.job_age_days = int(self.job_age_days)
        if self.max_results_total is not None:
            self.max_results_total = int(self.max_results_total)
        if self.max_results_per_source is not None:
            self.max_results_per_source = int(self.max_results_per_source)
        if self.llm_score_threshold is not None:
            self.llm_score_threshold = float(self.llm_score_threshold)
