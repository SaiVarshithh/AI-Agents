from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.schemas.research import ResearchStatus


@dataclass
class SessionRecord:
    session_id: str
    question: str
    status: ResearchStatus
    created_at: datetime
    completed_at: datetime | None = None
    report_markdown: str = ""
    sources: list[dict] = field(default_factory=list)
    sub_queries_used: list[str] = field(default_factory=list)
    critic_iterations: int = 0
    duration_seconds: float = 0.0


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}

    def create(self, session_id: str, question: str) -> SessionRecord:
        record = SessionRecord(
            session_id=session_id,
            question=question,
            status=ResearchStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        self._sessions[session_id] = record
        return record

    def get(self, session_id: str) -> SessionRecord | None:
        return self._sessions.get(session_id)

    def list(self) -> list[SessionRecord]:
        return sorted(self._sessions.values(), key=lambda s: s.created_at, reverse=True)

    def mark_running(self, session_id: str) -> None:
        session = self._sessions[session_id]
        session.status = ResearchStatus.RUNNING

    def mark_done(
        self,
        session_id: str,
        *,
        report_markdown: str,
        sources: list[dict],
        sub_queries_used: list[str],
        critic_iterations: int,
    ) -> None:
        session = self._sessions[session_id]
        session.status = ResearchStatus.DONE
        session.completed_at = datetime.now(timezone.utc)
        session.report_markdown = report_markdown
        session.sources = sources
        session.sub_queries_used = sub_queries_used
        session.critic_iterations = critic_iterations
        session.duration_seconds = (session.completed_at - session.created_at).total_seconds()

    def mark_failed(self, session_id: str) -> None:
        session = self._sessions[session_id]
        session.status = ResearchStatus.FAILED
        session.completed_at = datetime.now(timezone.utc)
        session.duration_seconds = (session.completed_at - session.created_at).total_seconds()
