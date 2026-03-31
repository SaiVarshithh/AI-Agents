from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Job:
    """Represents a single job posting scraped from any source."""

    title: str = ""
    company: str = ""
    location: str = ""
    experience: str = ""
    salary: str = ""
    posted_date: str = ""
    apply_url: str = ""
    description: str = ""
    tech_stack: list = field(default_factory=list)
    source: str = ""           # "naukri" | "monster" | ...
    job_id: str = ""
    job_type: str = ""         # full-time, contract, etc.
    industry: str = ""

    # LLM-generated fields
    relevance_score: float = 0.0
    match_summary: str = ""

    # LLM-generated detailed analysis
    llm_tech_stack: str = ""        # Tech stack breakdown from LLM
    llm_joining_period: str = ""    # Immediate / notice period / waiting period
    llm_location_detail: str = ""   # Remote / Hybrid / Onsite — city detail
    llm_detailed_summary: str = ""  # Multi-line detailed analysis

    # Tracking field (user-driven)
    applied: bool = False

    # --- convenience: backward compat with older kwargs ---
    experience_max: int = 0  # sometimes passed from site config

    def to_dict(self) -> dict:
        return {
            "Title": self.title,
            "Company": self.company,
            "Location": self.location,
            "Experience": self.experience,
            "Salary / CTC": self.salary,
            "Tech Stack": ", ".join(self.tech_stack) if self.tech_stack else "",
            "Posted Date": self.posted_date,
            "Job Type": self.job_type,
            "Industry": self.industry,
            "Source": self.source,
            "Apply URL": self.apply_url,
            "Relevance Score": self.relevance_score,
            "Match Summary": self.match_summary,
            "LLM Tech Stack": self.llm_tech_stack,
            "Joining / Notice": self.llm_joining_period,
            "Location Detail": self.llm_location_detail,
            "Detailed Analysis": self.llm_detailed_summary,
            "Applied": self.applied,
        }
