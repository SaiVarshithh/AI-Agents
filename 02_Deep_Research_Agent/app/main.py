from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.orchestrator.pipeline import ResearchPipeline
from app.schemas.research import (
    HealthResponse,
    ResearchRequest,
    ResearchResponse,
    SessionListItem,
    SessionListResponse,
)
from app.services.session_store import SessionStore

settings = get_settings()
configure_logging()

app = FastAPI(title=settings.APP_TITLE, version=settings.APP_VERSION)
store = SessionStore()
pipeline = ResearchPipeline()


def _to_response(record) -> ResearchResponse:
    return ResearchResponse(
        session_id=record.session_id,
        question=record.question,
        status=record.status,
        report_markdown=record.report_markdown,
        sources=record.sources,
        sub_queries_used=record.sub_queries_used,
        critic_iterations=record.critic_iterations,
        duration_seconds=record.duration_seconds,
        created_at=record.created_at,
        completed_at=record.completed_at,
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        llm_provider=settings.LLM_PROVIDER,
        database="in-memory",
    )


@app.get("/sessions", response_model=SessionListResponse)
async def list_sessions() -> SessionListResponse:
    sessions = [
        SessionListItem(
            session_id=s.session_id,
            question=s.question,
            status=s.status,
            created_at=s.created_at,
            duration_seconds=s.duration_seconds,
        )
        for s in store.list()
    ]
    return SessionListResponse(sessions=sessions, total=len(sessions))


@app.get("/sessions/{session_id}", response_model=ResearchResponse)
async def get_session(session_id: str) -> ResearchResponse:
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _to_response(session)


@app.post("/research")
async def research(request: ResearchRequest):
    session_id = str(uuid4())
    store.create(session_id=session_id, question=request.question)

    async def event_stream():
        store.mark_running(session_id)
        all_sources: dict[str, dict] = {}
        report_md = ""
        sub_queries: list[str] = []
        critic_iters = 0
        try:
            async for event in pipeline.run(
                question=request.question,
                max_sub_queries=request.max_sub_queries,
                max_critic_retries=request.max_critic_retries,
            ):
                if event.role.value == "planner":
                    sub_queries = event.payload.get("sub_queries", []) if event.payload else []
                if event.role.value == "summarizer" and event.payload:
                    for s in event.payload.get("summaries", []):
                        all_sources[s.get("url", str(len(all_sources)))] = s
                if event.role.value == "critic":
                    critic_iters += 1
                if event.role.value == "synthesizer" and event.payload:
                    report_md = event.payload.get("report_markdown", "")

                data = event.model_dump()
                yield f"event: {event.event}\ndata: {json.dumps(data)}\n\n"

            store.mark_done(
                session_id,
                report_markdown=report_md,
                sources=list[dict](all_sources.values()),
                sub_queries_used=sub_queries,
                critic_iterations=max(0, critic_iters - 1),
            )
            done_payload = {"session_id": session_id, "status": "done"}
            yield f"event: complete\ndata: {json.dumps(done_payload)}\n\n"
        except Exception as exc:
            store.mark_failed(session_id)
            err = {"session_id": session_id, "error": str(exc)}
            yield f"event: error\ndata: {json.dumps(err)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
