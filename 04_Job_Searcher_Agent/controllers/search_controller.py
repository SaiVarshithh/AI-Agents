import time
from typing import List
import json
import subprocess
import sys
import os
import logging
import concurrent.futures
from models.job import Job
from models.search_config import SearchConfig
from services.scrapers.registry import SiteRegistry
from services.llm.hf_llm import HuggingFaceLLM
from utils.date_utils import is_within_days
from utils.llm_cache import LLMCache

logger = logging.getLogger(__name__)

# Absolute path to the project root (one level up from controllers/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKER_SCRIPT = os.path.join(PROJECT_ROOT, "scrape_worker.py")


class SearchController:
    """
    Orchestrates the full pipeline:
      1. Run scrapers for each configured source (each in its own subprocess)
      2. Deduplicate jobs
      3. Optionally score with LLM
      4. Sort by relevance score
    """

    def __init__(self, config: SearchConfig):
        self.config = config
        self.llm = None

        if config.enable_llm_scoring:
            from services.llm.ensemble_llm import EnsembleLLM
            from config.settings import settings
            drivers = []
            
            if config.hf_token:
                # Speed: don't run *all* HF models for every job.
                # Use the user-selected HF model, plus one stable summarization fallback.
                from services.llm.hf_llm import HuggingFaceLLM
                if config.hf_model and not config.hf_model.startswith("ollama/"):
                    drivers.append(HuggingFaceLLM(config))
                if config.hf_model != "facebook/bart-large-cnn" and "facebook/bart-large-cnn" in settings.SUPPORTED_MODELS:
                    cfg2 = SearchConfig(**{**config.__dict__, "hf_model": "facebook/bart-large-cnn"})
                    drivers.append(HuggingFaceLLM(cfg2))
                    
            from services.llm.ollama_llm import OllamaLLM
            ollama_models = [m for m in settings.SUPPORTED_MODELS if m.startswith("ollama/")]
            if ollama_models:
                # Add default or selected ollama model
                target_ollama = config.hf_model if config.hf_model.startswith("ollama/") else ollama_models[0]
                drivers.append(OllamaLLM(config, model=target_ollama))

            self.llm = EnsembleLLM(config, drivers)

        self.registry = SiteRegistry(
            sites_dir=os.path.join(PROJECT_ROOT, "config", "sites")
        )

    def run(self, progress_callback=None) -> List[Job]:
        logger.info("Starting job search")

        def _emit(msg: str, progress: float | None = None):
            if not progress_callback:
                return
            if progress is None:
                progress_callback(msg)
            else:
                p = max(0.0, min(1.0, float(progress)))
                progress_callback(f"__PROGRESS__:{p:.3f}:{msg}")

        if self.config.candidate_resume_text and not self.config.keywords and self.llm and self.llm.drivers:
            # We need keywords to search Indeed/Monster, extract them!
            logger.info("Extracting search keywords from resume...")
            _emit("🧠 Analyzing your resume to extract search keywords and tech stack...", progress=0.05)
            
            prompt = f"<s>[INST] Extract the primary job title and the top 10 technical skills from this resume.\n\nRules:\n- TECH_STACK must include languages, frameworks, databases, cloud/devops/tools, and data/ML tools if present.\n- Prefer canonical names (e.g., FastAPI, PostgreSQL, MLflow, Airflow, Spark, Kubernetes, Docker, GraphQL, REST).\n- Keep TECH_STACK as a comma-separated list.\n\nResume excerpt:\n{self.config.candidate_resume_text[:3000]}\n\nRespond ONLY in this format:\nKEYWORDS: <Job Title>\nTECH_STACK: <Skill 1, Skill 2, ... Skill 10>[/INST]"
            result = ""
            
            for driver in self.llm.drivers:
                try:
                    res = driver.generate_text(prompt, max_tokens=100)
                    if res and "KEYWORDS:" in res:
                        result = res
                        logger.info(f"LLM Resume extraction succeeded via {driver.__class__.__name__} ({getattr(driver, 'model', 'default')})")
                        break
                except Exception as e:
                    logger.warning(f"Driver {driver.__class__.__name__} failed extraction: {e}")
                    
            if not result:
                logger.error("All LLM drivers failed to extract resume keywords!")
                _emit("❌ Error: All LLMs failed. Please provide keywords manually.", progress=0.08)
            else:
                logger.info(f"LLM Resume extraction result:\n{result}")
                _emit(f"📄 Resume analyzed. Extraction:\n{result}", progress=0.10)
                
                for line in result.split('\n'):
                    line = line.strip()
                    if line.startswith("KEYWORDS:") and not self.config.keywords:
                        self.config.keywords = line.replace("KEYWORDS:", "").strip()
                    if line.startswith("TECH_STACK:") and not self.config.tech_stacks:
                        techs = line.replace("TECH_STACK:", "").strip()
                        self.config.tech_stacks = [t.strip() for t in techs.split(",") if t.strip()]

        logger.info(f"Final Query Parameters => Keywords: '{self.config.keywords}', Locations: '{self.config.locations}'")
        
        all_jobs: List[Job] = []

        site_cfgs = {c.name.lower(): c for c in self.registry.list_site_configs()}
        logger.info(f"Available sites: {list(site_cfgs.keys())}")

        # Prepare tasks
        tasks = []
        for source in self.config.sources:
            site = site_cfgs.get(source.lower())
            if not site:
                logger.warning(f"Unknown/unconfigured source: {source}")
                if progress_callback:
                    progress_callback(f"⚠️ Unknown source (no config found): {source}")
                continue
            config_dict = {
                "keywords": self.config.keywords,
                "locations": self.config.locations,
                "job_age_days": self.config.job_age_days,
                "max_results_per_source": self.config.max_results_per_source,
                "playwright_enabled": self.config.playwright_enabled,
                "playwright_headless": self.config.playwright_headless,
                "playwright_storage_state_path": self.config.playwright_storage_state_path,
                # Pass LLM config so LLMPoweredScraper has access
                "hf_token": self.config.hf_token,
                "hf_model": self.config.hf_model,
                "enable_llm_scoring": self.config.enable_llm_scoring,
                "desired_role": self.config.desired_role,
                "tech_stacks": self.config.tech_stacks,
                "max_results_total": self.config.max_results_total,
            }
            site_dict = {
                "name": site.name,
                "strategy": site.strategy,
                "bootstrap_url": site.bootstrap_url,
                "search_url": site.search_url,
            }
            tasks.append((config_dict, site_dict, source))
            logger.info(f"Prepared task for {source}")

        logger.info(f"Running {len(tasks)} scraping tasks")

        results = []
        total_tasks = max(1, len(tasks))
        for config_dict, site_dict, source in tasks:
            logger.info(f"Starting subprocess for {source}")
            # Scraping phase occupies 10% -> 45%
            done = len(results)
            _emit(f"🔍 Scraping {source.capitalize()}...", progress=0.10 + (done / total_tasks) * 0.35)
            try:
                result = subprocess.run(
                    [sys.executable, WORKER_SCRIPT,
                     json.dumps(config_dict), json.dumps(site_dict)],
                    capture_output=True,
                    text=True,
                    cwd=PROJECT_ROOT,   # ← run from project root, not controllers/
                    timeout=120,
                )
                if result.returncode == 0:
                    if result.stderr:
                        for line in result.stderr.strip().split('\n'):
                            logger.info(f"[Worker {source}] {line}")
                    stdout = result.stdout.strip()
                    if not stdout:
                        results.append((source, [], "Worker returned empty output"))
                        continue
                    try:
                        jobs_data = json.loads(stdout)
                    except json.JSONDecodeError as e:
                        logger.error(f"Worker JSON decode error: {e}. Stdout was: {stdout[:200]}")
                        jobs_data = {"error": f"JSON decode error: {e}"}

                    if isinstance(jobs_data, list):
                        jobs = [Job(**j) for j in jobs_data]
                        results.append((source, jobs, None))
                        logger.info(f"Successfully scraped {len(jobs)} jobs from {source}")
                    else:
                        error = jobs_data.get("error", "Unknown error in worker")
                        results.append((source, [], error))
                else:
                    if result.stderr:
                        for line in result.stderr.strip().split('\n'):
                            logger.error(f"[Worker {source} ERROR] {line}")
                    error = result.stderr.strip()[-500:] if result.stderr else "Worker exited non-zero"
                    results.append((source, [], error))
                    logger.error(f"Failed to scrape {source}: {error}")
            except subprocess.TimeoutExpired:
                results.append((source, [], "Scraper timed out after 120s"))
                logger.error(f"Timeout scraping {source}")
            except Exception as e:
                results.append((source, [], str(e)))
                logger.error(f"Exception scraping {source}: {e}")
            finally:
                # Update progress after each scraper completes (successful or not)
                done2 = len(results)
                _emit(f"📦 Finished {source.capitalize()} scrape.", progress=0.10 + (done2 / total_tasks) * 0.35)

        for source, jobs, error in results:
            if error:
                logger.error(f"Scraper '{source}' failed: {error}")
                _emit(f"❌ {source.capitalize()} scraper failed: {error[:200]}")
            else:
                all_jobs.extend(jobs)
                _emit(f"✅ {source.capitalize()}: {len(jobs)} jobs found")

        # Deduplicate by (title + company)
        all_jobs = self._deduplicate(all_jobs)
        logger.info(f"After deduplication: {len(all_jobs)} jobs")

        # Recency filter
        if self.config.job_age_days is not None:
            before_filter = len(all_jobs)
            all_jobs = [j for j in all_jobs if is_within_days(j.posted_date, int(self.config.job_age_days))]
            logger.info(f"After recency filter ({self.config.job_age_days} days): {len(all_jobs)} jobs "
                        f"(filtered {before_filter - len(all_jobs)})")

        # LLM analysis (scoring + detailed breakdown)
        if self.llm and all_jobs:
            logger.info(f"Starting LLM analysis for {len(all_jobs)} jobs")
            _emit(f"🤖 Analyzing {len(all_jobs)} jobs with LLM...", progress=0.45)

            # Cache results across reruns (huge speedup for repeated searches)
            cache = LLMCache(os.path.join("output", "llm_cache.json"))

            # Phase 1: score ALL jobs fast (cheap) so we can rank them.
            def _score_one(j: Job):
                try:
                    # Use ensemble scoring (runs models concurrently internally)
                    score, summary = self.llm.score_job(j)
                    return j, float(score or 0.0), summary or ""
                except Exception as e:
                    return j, 0.0, f"LLM scoring unavailable ({e})"

            max_workers = min(12, max(2, (os.cpu_count() or 4)))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = [ex.submit(_score_one, j) for j in all_jobs]
                for idx, fut in enumerate(concurrent.futures.as_completed(futures), start=1):
                    j, sc, sm = fut.result()
                    j.relevance_score = sc
                    j.match_summary = sm
                    # scoring phase 45% -> 70% (update on every completion for smooth bar)
                    _emit(
                        f"🤖 Scored {idx}/{len(all_jobs)} jobs...",
                        progress=0.45 + (idx / max(1, len(all_jobs))) * 0.25,
                    )

            # Sort by score desc before detailed analysis
            all_jobs.sort(key=lambda j: (j.relevance_score, j.posted_date), reverse=True)

            # Phase 2: detailed analysis only for top-N jobs (scales to 1000+ jobs)
            top_n = min(len(all_jobs), int(getattr(self.config, "max_results_total", 50) or 50))
            to_analyze = all_jobs[:top_n]
            _emit(f"🤖 Deep-analyzing top {top_n}/{len(all_jobs)} jobs...", progress=0.70)

            def _analyze_one(j: Job):
                # Try cache per-driver best effort. For the ensemble, cache on the first driver's model.
                driver_model = getattr(self.llm.drivers[0], "model", "ensemble") if getattr(self.llm, "drivers", None) else "ensemble"
                key = cache.make_key(driver_model, j.job_id or "", j.apply_url or "", j.description or "")
                cached = cache.get(key)
                if isinstance(cached, dict):
                    return j, cached
                try:
                    res = self.llm.analyze_job_detailed(j)
                except Exception:
                    res = self.llm._fallback_analysis(j)
                if isinstance(res, dict) and res:
                    try:
                        cache.set(key, res)
                    except Exception as e:
                        logger.warning(f"LLM cache write failed, continuing without cache: {e}")
                return j, res

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = [ex.submit(_analyze_one, j) for j in to_analyze]
                for idx, fut in enumerate(concurrent.futures.as_completed(futures), start=1):
                    j, analysis = fut.result()
                    j.relevance_score = analysis.get("relevance_score", j.relevance_score or 0.0)
                    j.llm_tech_stack = analysis.get("tech_stack", "") or j.llm_tech_stack
                    j.llm_joining_period = analysis.get("joining_period", "") or j.llm_joining_period
                    j.llm_location_detail = analysis.get("location_detail", "") or j.llm_location_detail
                    j.llm_detailed_summary = analysis.get("detailed_summary", "") or j.llm_detailed_summary
                    # deep phase 70% -> 95% (update on every completion for smooth bar)
                    _emit(
                        f"🤖 Deep-analyzed {idx}/{top_n} jobs...",
                        progress=0.70 + (idx / max(1, top_n)) * 0.25,
                    )

            _emit(f"✅ LLM analysis completed for {len(all_jobs)} jobs", progress=0.95)
            logger.info("LLM analysis completed")
        elif all_jobs:
            # No LLM configured — use fallback analysis for structure
            logger.info("No LLM configured, using fallback analysis")
            if progress_callback:
                progress_callback(f"📋 Generating basic analysis for {len(all_jobs)} jobs...")
            from services.llm.hf_llm import HuggingFaceLLM
            # Create a temporary instance just for fallback analysis
            dummy_llm = HuggingFaceLLM.__new__(HuggingFaceLLM)
            dummy_llm.config = self.config
            for job in all_jobs:
                fallback = dummy_llm._fallback_analysis(job)
                job.llm_tech_stack = fallback["tech_stack"]
                job.llm_joining_period = fallback["joining_period"]
                job.llm_location_detail = fallback["location_detail"]
                job.llm_detailed_summary = fallback["detailed_summary"]

        # Filter by threshold
        if self.config.llm_score_threshold > 0:
            before_threshold = len(all_jobs)
            all_jobs = [j for j in all_jobs if j.relevance_score >= self.config.llm_score_threshold]
            logger.info(f"After threshold filter: {len(all_jobs)} jobs "
                        f"(filtered {before_threshold - len(all_jobs)})")

        # Sort: relevance desc, then posted date desc
        all_jobs.sort(key=lambda j: (j.relevance_score, j.posted_date), reverse=True)
        logger.info(f"Final sorted jobs: {len(all_jobs)}")

        return all_jobs[: self.config.max_results_total]

    def _deduplicate(self, jobs: List[Job]) -> List[Job]:
        seen = set()
        unique = []
        for job in jobs:
            key = (job.title.lower().strip(), job.company.lower().strip())
            if key not in seen:
                seen.add(key)
                unique.append(job)
        return unique