"""
Custom exception hierarchy for Deep Research Agent.

All domain errors extend ResearchAgentError so callers can catch
a single base type and still inspect the specific cause.
"""


class ResearchAgentError(Exception):
    """Base class for all application-level exceptions."""

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def __str__(self) -> str:
        if self.detail:
            return f"{self.message} — {self.detail}"
        return self.message


# ── LLM layer ──────────────────────────────────────────────────────────────

class LLMError(ResearchAgentError):
    """Raised when an LLM provider call fails."""


class LLMTimeoutError(LLMError):
    """Raised when an LLM call exceeds the configured timeout."""


class LLMParseError(LLMError):
    """Raised when the LLM response cannot be parsed into the expected format."""


class LLMProviderNotFoundError(LLMError):
    """Raised when an unknown LLM provider is configured."""


# ── Agent layer ─────────────────────────────────────────────────────────────

class AgentError(ResearchAgentError):
    """Raised when an agent fails to complete its task."""


class PlannerError(AgentError):
    """Raised when the Planner agent cannot decompose the question."""


class ResearcherError(AgentError):
    """Raised when the Researcher agent cannot retrieve search results."""


class SummarizerError(AgentError):
    """Raised when the Summarizer agent cannot summarize a source."""


class CriticError(AgentError):
    """Raised when the Critic agent cannot evaluate gathered evidence."""


class SynthesizerError(AgentError):
    """Raised when the Synthesizer agent cannot produce the final report."""


# ── Search layer ─────────────────────────────────────────────────────────────

class WebSearchError(ResearchAgentError):
    """Raised when the web search backend returns an error."""


class PageFetchError(ResearchAgentError):
    """Raised when a URL cannot be fetched or its content extracted."""


# ── Database layer ────────────────────────────────────────────────────────────

class DatabaseError(ResearchAgentError):
    """Raised when a database operation fails."""


class SessionNotFoundError(DatabaseError):
    """Raised when a research session ID does not exist."""


# ── Orchestration ─────────────────────────────────────────────────────────────

class OrchestratorError(ResearchAgentError):
    """Raised when the orchestrator encounters an unrecoverable state."""


class MaxRetriesExceededError(OrchestratorError):
    """Raised when the Critic's retry budget is exhausted."""
