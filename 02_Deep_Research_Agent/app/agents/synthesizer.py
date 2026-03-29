from __future__ import annotations

from app.schemas.agent import SynthesizerOutput
from app.services.llm import LLMClient


class SynthesizerAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def run(self, *, question: str, summaries: list[dict]) -> SynthesizerOutput:
        system_prompt = (
            "You synthesize research findings into markdown report with clear sections. "
            "Return plain markdown only."
        )
        user_prompt = (
            f"Question: {question}\n"
            f"Use these source summaries:\n{summaries}\n"
            "Structure: Executive Summary, Findings, Risks/Unknowns, Sources."
        )
        report = ""
        try:
            report = await self.llm.complete(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception:
            lines = [
                f"# Research Report\n\n## Question\n{question}\n",
                "## Findings",
            ]
            for idx, item in enumerate(summaries, start=1):
                lines.append(f"{idx}. **{item.get('title','Source')}** - {item.get('summary','')}")
            lines.append("\n## Sources")
            for item in summaries:
                lines.append(f"- {item.get('url','')}")
            report = "\n".join(lines)

        sources_used = list({item.get("url", "") for item in summaries if item.get("url")})
        return SynthesizerOutput(
            report_markdown=report.strip(),
            sources_used=sources_used,
            word_count=len(report.split()),
        )
