from __future__ import annotations

from app.schemas.agent import SourceSummary, SummarizerOutput
from app.services.llm import LLMClient


class SummarizerAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def run(self, *, query: str, sources: list[dict]) -> SummarizerOutput:
        summaries: list[SourceSummary] = []
        for source in sources:
            title = source.get("title", "")
            url = source.get("url", "")
            snippet = source.get("snippet", "")
            body = source.get("body", "")[:2500]
            system_prompt = (
                "You summarize one source into JSON with keys: "
                "'summary' (string) and 'key_facts' (array of short strings)."
            )
            user_prompt = (
                f"Question: {query}\nTitle: {title}\nURL: {url}\nSnippet: {snippet}\n"
                f"Body: {body}\nKeep concise and factual."
            )
            try:
                data = await self.llm.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
                summary = str(data.get("summary", snippet or body[:300])).strip()
                key_facts = [str(x).strip() for x in data.get("key_facts", []) if str(x).strip()]
            except Exception:
                summary = (snippet or body[:300] or "No summary available").strip()
                key_facts = [summary[:180]]
            summaries.append(
                SourceSummary(url=url, title=title or url, summary=summary, key_facts=key_facts[:5])
            )
        return SummarizerOutput(query=query, summaries=summaries)
