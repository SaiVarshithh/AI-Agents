from __future__ import annotations

from app.core.config import get_settings
from app.schemas.agent import ResearcherOutput
from app.services.web_search import WebSearchService


class ResearcherAgent:
    def __init__(self, web: WebSearchService) -> None:
        self.web = web
        self.settings = get_settings()

    async def run(self, query: str) -> ResearcherOutput:
        results = await self.web.search(query, max_results=self.settings.MAX_SOURCES_PER_QUERY)
        return ResearcherOutput(query=query, results=results)
