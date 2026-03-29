"""
Pydantic schemas for the public-facing Research API.
"""

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ResearchStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ResearchRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="The research question in plain English",
        examples=["What are the latest developments in quantum computing?"],
    )
    max_sub_queries: Optional[int] = Field(default=None, ge=1, le=8)
    max_critic_retries: Optional[int] = Field(default=None, ge=0, le=3)


class SourceReference(BaseModel):
    url: str
    title: str
    summary: str


class ResearchResponse(BaseModel):
    session_id: str
    question: str
    status: ResearchStatus
    report_markdown: str = ""
    sources: list[SourceReference] = Field(default_factory=list)
    sub_queries_used: list[str] = Field(default_factory=list)
    critic_iterations: int = 0
    duration_seconds: float = 0.0
    created_at: datetime
    completed_at: Optional[datetime] = None


class SessionListItem(BaseModel):
    session_id: str
    question: str
    status: ResearchStatus
    created_at: datetime
    duration_seconds: float = 0.0


class SessionListResponse(BaseModel):
    sessions: list[SessionListItem]
    total: int


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_provider: str
    database: str
