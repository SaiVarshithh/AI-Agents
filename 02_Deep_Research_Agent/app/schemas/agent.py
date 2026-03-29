"""
Pydantic schemas for agent inputs and outputs.
These are data-transfer objects — not ORM entities.
"""

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional


class AgentRole(str, Enum):
    PLANNER = "planner"
    RESEARCHER = "researcher"
    SUMMARIZER = "summarizer"
    CRITIC = "critic"
    SYNTHESIZER = "synthesizer"


class AgentEvent(BaseModel):
    """
    A structured event emitted by an agent during the pipeline.
    Streamed to the client via SSE.
    """
    role: AgentRole
    event: str                        # e.g. "started", "progress", "done", "error"
    message: str                      # Human-readable status
    payload: Optional[dict] = None    # Optional structured data


# ── Planner ──────────────────────────────────────────────────────────────────

class PlannerOutput(BaseModel):
    sub_queries: list[str] = Field(..., min_length=1)
    reasoning: str = ""


# ── Researcher ────────────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    body: str = ""       # Fetched page content (truncated)


class ResearcherOutput(BaseModel):
    query: str
    results: list[SearchResult]


# ── Summarizer ────────────────────────────────────────────────────────────────

class SourceSummary(BaseModel):
    url: str
    title: str
    summary: str
    key_facts: list[str] = Field(default_factory=list)


class SummarizerOutput(BaseModel):
    query: str
    summaries: list[SourceSummary]


# ── Critic ────────────────────────────────────────────────────────────────────

class CriticVerdict(str, Enum):
    SUFFICIENT = "sufficient"
    NEEDS_MORE = "needs_more"


class CriticOutput(BaseModel):
    verdict: CriticVerdict
    reasoning: str
    additional_queries: list[str] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.5)


# ── Synthesizer ───────────────────────────────────────────────────────────────

class SynthesizerOutput(BaseModel):
    report_markdown: str
    sources_used: list[str]           # List of URLs cited
    word_count: int = 0
