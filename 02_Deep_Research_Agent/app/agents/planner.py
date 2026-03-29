from __future__ import annotations

import re

from app.core.config import get_settings
from app.schemas.agent import PlannerOutput
from app.services.llm import LLMClient


class PlannerAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.settings = get_settings()

    async def run(self, question: str, max_sub_queries: int | None = None) -> PlannerOutput:
        limit = max_sub_queries or self.settings.MAX_SUB_QUERIES
        system_prompt = (
            "You are a planning agent. Return strict JSON with keys "
            "'sub_queries' (array of strings) and 'reasoning' (string)."
        )
        user_prompt = f"Question: {question}\nGenerate at most {limit} focused sub-queries."
        try:
            data = await self.llm.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
            queries = [q.strip() for q in data.get("sub_queries", []) if isinstance(q, str) and q.strip()]
            if queries:
                return PlannerOutput(sub_queries=queries[:limit], reasoning=str(data.get("reasoning", "")))
        except Exception:
            pass

        split = re.split(r"[?.!;]\s+| and |, ", question)
        queries = [q.strip() for q in split if len(q.strip()) > 8]
        if not queries:
            queries = [question]
        return PlannerOutput(sub_queries=queries[:limit], reasoning="Fallback heuristic planner")
