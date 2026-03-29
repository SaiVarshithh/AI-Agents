from __future__ import annotations

import re
from html import unescape
from urllib.parse import quote_plus

import httpx

from app.core.config import get_settings
from app.core.exceptions import PageFetchError, WebSearchError
from app.schemas.agent import SearchResult


class WebSearchService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def search(self, query: str, *, max_results: int | None = None) -> list[SearchResult]:
        limit = max_results or self.settings.SEARCH_MAX_RESULTS
        api = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_redirect=1&no_html=1"
        try:
            async with httpx.AsyncClient(timeout=self.settings.PAGE_FETCH_TIMEOUT) as client:
                res = await client.get(api)
                if res.status_code >= 400:
                    raise WebSearchError("DuckDuckGo request failed", detail=res.text[:300])
                data = res.json()
        except Exception as exc:
            if isinstance(exc, WebSearchError):
                raise
            raise WebSearchError("Search request failed", detail=str(exc)) from exc

        results: list[SearchResult] = []
        for topic in data.get("RelatedTopics", []):
            if isinstance(topic, dict) and "Topics" in topic:
                candidates = topic["Topics"]
            else:
                candidates = [topic]
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                url = item.get("FirstURL", "")
                text = item.get("Text", "")
                if not url or not text:
                    continue
                title = text.split(" - ")[0].strip()
                snippet = text.strip()
                body = await self.fetch_page_text(url)
                results.append(SearchResult(title=title, url=url, snippet=snippet, body=body))
                if len(results) >= limit:
                    return results
        return results

    async def fetch_page_text(self, url: str) -> str:
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.PAGE_FETCH_TIMEOUT, follow_redirects=True
            ) as client:
                res = await client.get(url)
                if res.status_code >= 400:
                    raise PageFetchError("Page fetch failed", detail=f"{url} => {res.status_code}")
                html = res.text
        except Exception as exc:
            if isinstance(exc, PageFetchError):
                raise
            raise PageFetchError("Page fetch failed", detail=f"{url}: {exc}") from exc

        cleaned = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
        cleaned = re.sub(r"<style[\s\S]*?</style>", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", unescape(cleaned)).strip()
        return cleaned[: self.settings.PAGE_MAX_CHARS]
