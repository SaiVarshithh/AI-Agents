from __future__ import annotations

from app.schemas.agent import CriticOutput, CriticVerdict
from app.services.llm import LLMClient


class CriticAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def run(self, *, question: str, summaries: list[dict], retry_count: int) -> CriticOutput:
        system_prompt = (
            "You are a research critic. Return strict JSON keys: "
            "'verdict' ('sufficient'|'needs_more'), 'reasoning' (string), "
            "'additional_queries' (array), 'confidence_score' (0..1)."
        )
        user_prompt = (
            f"Question: {question}\nCurrent summary count: {len(summaries)}\n"
            f"Retry count used: {retry_count}\nSummaries: {summaries[:4]}"
        )
        try:
            data = await self.llm.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
            verdict_text = str(data.get("verdict", "sufficient")).lower()
            verdict = CriticVerdict.NEEDS_MORE if verdict_text == "needs_more" else CriticVerdict.SUFFICIENT
            additional = [str(x).strip() for x in data.get("additional_queries", []) if str(x).strip()]
            confidence = float(data.get("confidence_score", 0.7))
            confidence = max(0.0, min(1.0, confidence))
            return CriticOutput(
                verdict=verdict,
                reasoning=str(data.get("reasoning", "")),
                additional_queries=additional[:3],
                confidence_score=confidence,
            )
        except Exception:
            if len(summaries) >= 3 or retry_count >= 1:
                return CriticOutput(
                    verdict=CriticVerdict.SUFFICIENT,
                    reasoning="Fallback critic judged evidence as sufficient.",
                    confidence_score=0.6,
                )
            return CriticOutput(
                verdict=CriticVerdict.NEEDS_MORE,
                reasoning="Fallback critic requested one more targeted query.",
                additional_queries=[f"{question} latest developments"],
                confidence_score=0.45,
            )
