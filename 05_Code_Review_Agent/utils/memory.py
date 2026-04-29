"""
File-based memory for persisting code review history across sessions.
"""
import json
import uuid
from datetime import datetime
from pathlib import Path


HISTORY_FILE = Path(__file__).parent.parent / "data" / "review_history.json"


def _load_history() -> list[dict]:
    """Load review history from disk."""
    if not HISTORY_FILE.exists():
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_history(history: list[dict]) -> None:
    """Persist review history to disk."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def save_review(
    code_snippet: str,
    language: str,
    report: dict,
    model_used: str,
) -> str:
    """Save a completed review to history. Returns the review ID."""
    history = _load_history()
    review_id = str(uuid.uuid4())[:8]
    entry = {
        "id": review_id,
        "timestamp": datetime.now().isoformat(),
        "language": language,
        "model": model_used,
        "code_preview": code_snippet[:200] + ("..." if len(code_snippet) > 200 else ""),
        "line_count": len(code_snippet.splitlines()),
        "summary": {
            "total_issues": report.get("total_issues", 0),
            "critical": report.get("critical_count", 0),
            "warnings": report.get("warning_count", 0),
            "overall_score": report.get("overall_score", "N/A"),
        },
    }
    history.insert(0, entry)   # newest first
    history = history[:50]      # cap at 50 entries
    _save_history(history)
    return review_id


def get_history() -> list[dict]:
    """Return all stored reviews (newest first)."""
    return _load_history()


def get_review_by_id(review_id: str) -> dict | None:
    """Fetch a specific review by ID."""
    for entry in _load_history():
        if entry["id"] == review_id:
            return entry
    return None


def clear_history() -> None:
    """Wipe all stored reviews."""
    _save_history([])


def get_stats() -> dict:
    """Aggregate stats across all stored reviews."""
    history = _load_history()
    if not history:
        return {"total_reviews": 0}

    total_issues = sum(r["summary"]["total_issues"] for r in history)
    total_critical = sum(r["summary"]["critical"] for r in history)
    languages = {}
    for r in history:
        lang = r.get("language", "unknown")
        languages[lang] = languages.get(lang, 0) + 1

    return {
        "total_reviews": len(history),
        "total_issues_found": total_issues,
        "total_critical": total_critical,
        "languages_reviewed": languages,
        "last_review": history[0]["timestamp"] if history else None,
    }