import concurrent.futures
import logging
from typing import List
from models.job import Job
from models.search_config import SearchConfig
from .base_llm import BaseLLM

logger = logging.getLogger(__name__)

class EnsembleLLM(BaseLLM):
    """
    Runs multiple LLM providers concurrently for a single job
    and averages/merges the results.
    """
    def __init__(self, config: SearchConfig, drivers: List[BaseLLM]):
        super().__init__(config)
        self.drivers = drivers

    def score_job(self, job: Job) -> tuple:
        """Run score_job across all drivers concurrently and return averaged score + merged summary."""
        if not self.drivers:
            return 0.0, "No LLM drivers configured"

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.drivers)) as executor:
            future_to_driver = {executor.submit(d.score_job, job): d for d in self.drivers}
            for future in concurrent.futures.as_completed(future_to_driver):
                driver = future_to_driver[future]
                try:
                    score, summary = future.result()
                    if score > 0 or summary:
                        driver_name = getattr(driver, "model", driver.__class__.__name__)
                        results.append((score, f"({driver_name}): {summary}"))
                except Exception as e:
                    logger.error(f"Driver {driver.__class__.__name__} score_job failed: {e}")

        if not results:
            return 0.0, "LLM scoring unavailable"

        avg_score = sum(r[0] for r in results) / len(results)
        combined_summary = " | ".join(r[1] for r in results)
        return avg_score, combined_summary

    def analyze_job_detailed(self, job: Job) -> dict:
        if not self.drivers:
            return {}

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.drivers)) as executor:
            future_to_driver = {executor.submit(d.analyze_job_detailed, job): d for d in self.drivers}
            for future in concurrent.futures.as_completed(future_to_driver):
                driver = future_to_driver[future]
                try:
                    res = future.result()
                    # if a driver returned the fallback due to failure, skip adding if we have alternatives
                    if res.get("relevance_score", 0) > 0 or res.get("detailed_summary") and not "Salary not disclosed" in res.get("detailed_summary", ""):
                        # Append the result with a marker of what driver it came from
                        driver_name = getattr(driver, "model", driver.__class__.__name__)
                        res["_source_driver"] = driver_name
                        results.append(res)
                except Exception as e:
                    logger.error(f"Driver {driver.__class__.__name__} failed: {e}")

        if not results:
            return self._fallback_analysis(job)

        # Aggregate the results
        valid_scores = [float(r.get("relevance_score", 0.0)) for r in results]
        avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
        
        # Combine summaries
        summaries = [f"({r.get('_source_driver', 'LLM')}): {r.get('detailed_summary', '').replace('SUMMARY:', '').strip()}" for r in results if r.get('detailed_summary')]
        combined_summary = "\n\n".join(summaries)
        
        # Pick tech stack and location from first valid result
        tech_stack = results[0].get("tech_stack", "")
        joining = results[0].get("joining_period", "")
        loc = results[0].get("location_detail", "")

        return {
            "relevance_score": avg_score,
            "tech_stack": tech_stack,
            "joining_period": joining,
            "location_detail": loc,
            "detailed_summary": combined_summary,
        }

    def _fallback_analysis(self, job: Job) -> dict:
        if self.drivers:
            if hasattr(self.drivers[0], "_fallback_analysis"):
                return self.drivers[0]._fallback_analysis(job)
        return {
            "relevance_score": 0.0,
            "tech_stack": "—",
            "joining_period": "—",
            "location_detail": "—",
            "detailed_summary": "LLM Analysis failed across all models."
        }
