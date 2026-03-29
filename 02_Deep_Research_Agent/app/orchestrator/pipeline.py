from __future__ import annotations

from app.agents.critic import CriticAgent
from app.agents.planner import PlannerAgent
from app.agents.researcher import ResearcherAgent
from app.agents.summarizer import SummarizerAgent
from app.agents.synthesizer import SynthesizerAgent
from app.core.config import get_settings
from app.schemas.agent import AgentEvent, AgentRole, CriticVerdict
from app.services.llm import LLMClient
from app.services.web_search import WebSearchService


class ResearchPipeline:
    def __init__(self) -> None:
        self.settings = get_settings()
        llm = LLMClient()
        web = WebSearchService()
        self.planner = PlannerAgent(llm)
        self.researcher = ResearcherAgent(web)
        self.summarizer = SummarizerAgent(llm)
        self.critic = CriticAgent(llm)
        self.synthesizer = SynthesizerAgent(llm)

    async def run(
        self,
        *,
        question: str,
        max_sub_queries: int | None = None,
        max_critic_retries: int | None = None,
    ):
        retries_cap = (
            self.settings.MAX_CRITIC_RETRIES if max_critic_retries is None else max_critic_retries
        )
        planner_output = await self.planner.run(question, max_sub_queries=max_sub_queries)
        yield AgentEvent(
            role=AgentRole.PLANNER,
            event="done",
            message=f"Planner generated {len(planner_output.sub_queries)} sub-queries",
            payload=planner_output.model_dump(),
        )

        all_summaries: list[dict] = []
        all_sub_queries = list(planner_output.sub_queries)
        critic_iterations = 0
        pending_queries = list(planner_output.sub_queries)

        while pending_queries:
            next_queries = pending_queries
            pending_queries = []
            for query in next_queries:
                yield AgentEvent(
                    role=AgentRole.RESEARCHER,
                    event="started",
                    message=f"Researching: {query}",
                )
                researcher_output = await self.researcher.run(query)
                yield AgentEvent(
                    role=AgentRole.RESEARCHER,
                    event="done",
                    message=f"Found {len(researcher_output.results)} sources",
                    payload=researcher_output.model_dump(),
                )

                sources = [r.model_dump() for r in researcher_output.results]
                summarizer_output = await self.summarizer.run(query=query, sources=sources)
                all_summaries.extend([s.model_dump() for s in summarizer_output.summaries])
                yield AgentEvent(
                    role=AgentRole.SUMMARIZER,
                    event="done",
                    message=f"Summarized {len(summarizer_output.summaries)} sources",
                    payload=summarizer_output.model_dump(),
                )

            critic_output = await self.critic.run(
                question=question, summaries=all_summaries, retry_count=critic_iterations
            )
            yield AgentEvent(
                role=AgentRole.CRITIC,
                event="done",
                message=f"Critic verdict: {critic_output.verdict.value}",
                payload=critic_output.model_dump(),
            )
            if critic_output.verdict == CriticVerdict.SUFFICIENT:
                break
            if critic_iterations >= retries_cap:
                break
            pending_queries = critic_output.additional_queries or []
            all_sub_queries.extend(pending_queries)
            critic_iterations += 1

        synth = await self.synthesizer.run(question=question, summaries=all_summaries)
        yield AgentEvent(
            role=AgentRole.SYNTHESIZER,
            event="done",
            message="Final report generated",
            payload=synth.model_dump(),
        )
