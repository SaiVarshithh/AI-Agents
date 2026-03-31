from __future__ import annotations

import json
import logging
import re
import sys
import asyncio
import time
from typing import List
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from config.settings import settings
from models.job import Job
from models.search_config import SearchConfig
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)


# ─── Search URL templates for each platform ──────────────────────────────────
PLATFORM_URLS = {
    "naukri": "https://www.naukri.com/{kw}-jobs-in-{loc}?k={kw_q}&l={loc_q}&jobAge={age}",
    "foundit": "https://www.foundit.in/srp/results?query={kw_q}&locations={loc_q}&postedDate={age}",
    "indeed": "https://in.indeed.com/jobs?q={kw_q}&l={loc_q}&fromage={age}",
    "linkedin": "https://www.linkedin.com/jobs/search/?keywords={kw_q}&location={loc_q}&f_TPR=r{age_s}",
    "shine": "https://www.shine.com/job-search/{kw_slug}-jobs-in-{loc_slug}/?updated_at_range={age}d",
    "timesjobs": "https://www.timesjobs.com/candidate/job-search.html?searchType=personalizedSearch&from=submit&txtKeywords={kw_q}&txtLocation={loc_q}",
}


class LLMPoweredScraper(BaseScraper):
    """
    Playwright-powered scraper that browses Indian job platforms
    exactly how a human (or LLM) would — by navigating to the search
    results page and extracting job cards from the live HTML.

    Falls back gracefully: tries multiple platforms and returns all
    jobs found across them.
    """

    SOURCE_NAME: str = "llm_powered"

    def __init__(self, config: SearchConfig):
        super().__init__(config)

    def fetch_jobs(self) -> List[Job]:
        logger.info("Starting LLM-powered (Playwright real-browse) job scraping")
        self._ensure_windows_event_loop_policy()

        keywords = self.config.keywords or "software developer"
        locations = self.config.locations or ["India"]
        location = locations[0] if locations else "India"
        age = getattr(self.config, "job_age_days", 7)
        target = getattr(self.config, "max_results_per_source", 25)

        kw_q = quote_plus(keywords)
        loc_q = quote_plus(location)
        kw_slug = re.sub(r"[^a-z0-9]+", "-", keywords.lower()).strip("-")
        loc_slug = re.sub(r"[^a-z0-9]+", "-", location.lower()).strip("-")
        age_s = str(int(age) * 86400)  # seconds for LinkedIn

        # platforms to try in priority order
        platforms_to_try = [
            (
                "naukri",
                PLATFORM_URLS["naukri"].format(
                    kw=kw_slug, loc=loc_slug, kw_q=kw_q, loc_q=loc_q, age=age
                ),
            ),
            (
                "foundit",
                PLATFORM_URLS["foundit"].format(
                    kw_q=kw_q, loc_q=loc_q, age=age
                ),
            ),
            (
                "indeed",
                PLATFORM_URLS["indeed"].format(
                    kw_q=kw_q, loc_q=loc_q, age=age
                ),
            ),
            (
                "shine",
                PLATFORM_URLS["shine"].format(
                    kw_slug=kw_slug, loc_slug=loc_slug, age=age
                ),
            ),
        ]

        all_jobs: List[Job] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.config.playwright_headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1366, "height": 768},
                locale="en-IN",
            )
            ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            for platform, url in platforms_to_try:
                if len(all_jobs) >= target:
                    break
                try:
                    logger.info(f"LLM scraper: browsing {platform} → {url}")
                    page = ctx.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=40000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                    page.wait_for_timeout(3000)

                    html = page.content()
                    page.close()

                    jobs = self._extract_jobs(platform, html, keywords, location)
                    logger.info(f"LLM scraper: extracted {len(jobs)} jobs from {platform}")
                    all_jobs.extend(jobs)
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"LLM scraper: failed on {platform}: {e}")
                    try:
                        page.close()
                    except Exception:
                        pass
                    continue

            ctx.close()
            browser.close()

        logger.info(f"LLM scraper total: {len(all_jobs)} jobs")
        return all_jobs[:target]

    # ─── Per-platform parsers ─────────────────────────────────────────────────

    def _extract_jobs(self, platform: str, html: str, keywords: str, location: str) -> List[Job]:
        soup = BeautifulSoup(html, "lxml")

        if platform == "naukri":
            return self._parse_naukri(soup, keywords, location)
        elif platform == "foundit":
            return self._parse_foundit(soup, keywords, location)
        elif platform == "indeed":
            return self._parse_indeed(soup, keywords, location)
        elif platform == "shine":
            return self._parse_shine(soup, keywords, location)
        else:
            return self._parse_generic(soup, platform, keywords, location)

    def _parse_naukri(self, soup: BeautifulSoup, keywords: str, location: str) -> List[Job]:
        jobs = []
        cards = (
            soup.find_all("article", class_=re.compile(r"jobTuple", re.I))
            or soup.find_all("div", class_=re.compile(r"jobTuple", re.I))
            or soup.find_all(attrs={"data-job-id": True})
        )
        for card in cards[:self.config.max_results_per_source]:
            try:
                title_el = (
                    card.find("a", class_=re.compile(r"title", re.I))
                    or card.find("a", attrs={"title": True})
                )
                title = _strip(title_el) if title_el else ""
                url = title_el.get("href", "") if title_el else ""
                if url.startswith("/"):
                    url = "https://www.naukri.com" + url
                company = _strip(card.find(class_=re.compile(r"comp|company", re.I)))
                loc = _strip(card.find(class_=re.compile(r"loc|location", re.I)))
                exp = _strip(card.find(class_=re.compile(r"exp", re.I)))
                sal = _strip(card.find(class_=re.compile(r"sal", re.I)))
                job_id = url.split("?")[0].rstrip("/").split("-")[-1] if url else ""
                if not title:
                    continue
                jobs.append(_make_job("naukri", job_id, title, company, loc, exp, sal, "", url))
            except Exception:
                continue
        return jobs

    def _parse_foundit(self, soup: BeautifulSoup, keywords: str, location: str) -> List[Job]:
        jobs = []
        cards = (
            soup.find_all("div", class_=re.compile(r"card-apply-content|srpResultCard|jobCard", re.I))
            or soup.find_all(attrs={"data-job-id": True})
            or soup.find_all("div", class_=re.compile(r"job.?card|result.?card", re.I))
        )
        for card in cards[:self.config.max_results_per_source]:
            try:
                title_el = (
                    card.find("a", class_=re.compile(r"title", re.I))
                    or card.find("h3") or card.find("h2")
                )
                title = _strip(title_el) if title_el else ""
                url = title_el.get("href", "") if title_el else ""
                if url.startswith("/"):
                    url = "https://www.foundit.in" + url
                company = _strip(card.find(class_=re.compile(r"company|employer", re.I)))
                loc = _strip(card.find(class_=re.compile(r"location|loc", re.I)))
                exp = _strip(card.find(class_=re.compile(r"exp", re.I)))
                sal = _strip(card.find(class_=re.compile(r"sal|ctc|salary", re.I)))
                job_id = card.get("data-job-id", "") or url.split("/")[-1].split("?")[0]
                if not title:
                    continue
                jobs.append(_make_job("foundit", str(job_id), title, company, loc, exp, sal, "", url))
            except Exception:
                continue
        return jobs

    def _parse_indeed(self, soup: BeautifulSoup, keywords: str, location: str) -> List[Job]:
        jobs = []
        cards = soup.find_all("div", class_="job_seen_beacon")
        for card in cards[:self.config.max_results_per_source]:
            try:
                title_el = card.find("span", id=lambda x: x and x.startswith("jobTitle"))
                if not title_el:
                    continue
                title = _strip(title_el)
                link_el = card.find("a", href=True)
                url = link_el["href"] if link_el else ""
                if url.startswith("/"):
                    url = "https://in.indeed.com" + url
                company = _strip(card.find(attrs={"data-testid": "company-name"}))
                loc = _strip(card.find(attrs={"data-testid": "text-location"}))
                job_id = url.split("?")[0].split("/")[-1]
                jobs.append(_make_job("indeed", job_id, title, company, loc, "", "", "", url))
            except Exception:
                continue
        return jobs

    def _parse_shine(self, soup: BeautifulSoup, keywords: str, location: str) -> List[Job]:
        jobs = []
        cards = soup.find_all("div", class_=re.compile(r"job-list|jobCard|job_listing", re.I))
        for card in cards[:self.config.max_results_per_source]:
            try:
                title_el = card.find("a", class_=re.compile(r"title|heading", re.I)) or card.find("h3")
                title = _strip(title_el) if title_el else ""
                url = title_el.get("href", "") if title_el else ""
                if url.startswith("/"):
                    url = "https://www.shine.com" + url
                company = _strip(card.find(class_=re.compile(r"company|employer", re.I)))
                loc = _strip(card.find(class_=re.compile(r"location|loc", re.I)))
                exp = _strip(card.find(class_=re.compile(r"exp", re.I)))
                job_id = url.split("?")[0].rstrip("/").split("-")[-1] if url else ""
                if not title:
                    continue
                jobs.append(_make_job("shine", job_id, title, company, loc, exp, "", "", url))
            except Exception:
                continue
        return jobs

    def _parse_generic(self, soup: BeautifulSoup, platform: str, keywords: str, location: str) -> List[Job]:
        """Generic fallback — tries common job card patterns."""
        jobs = []
        # Try common container patterns
        cards = (
            soup.find_all(attrs={"data-job-id": True})
            or soup.find_all("div", class_=re.compile(r"job.?card|result.?item|job.?listing|job.?post", re.I))
            or soup.find_all("li", class_=re.compile(r"job.?item|result", re.I))
        )
        for card in cards[:self.config.max_results_per_source]:
            try:
                title_el = card.find(["h2", "h3", "a"], class_=re.compile(r"title|heading", re.I))
                if not title_el:
                    continue
                title = _strip(title_el)
                url = title_el.get("href", "") if hasattr(title_el, "get") else ""
                company = _strip(card.find(class_=re.compile(r"company|employer|org", re.I)))
                loc = _strip(card.find(class_=re.compile(r"location|loc|city", re.I)))
                if not title:
                    continue
                jobs.append(_make_job(platform, "", title, company, loc, "", "", "", url))
            except Exception:
                continue
        return jobs

    # ─── Windows event loop fix ───────────────────────────────────────────────

    def _ensure_windows_event_loop_policy(self) -> None:
        if sys.platform != "win32":
            return
        policy_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
        if policy_cls is None:
            return
        try:
            current = asyncio.get_event_loop_policy()
            if not isinstance(current, policy_cls):
                asyncio.set_event_loop_policy(policy_cls())
        except Exception:
            pass


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _strip(el) -> str:
    if el is None:
        return ""
    return " ".join(el.get_text().split()).strip()


def _make_job(
    source: str,
    job_id: str,
    title: str,
    company: str,
    location: str,
    experience: str,
    salary: str,
    description: str,
    apply_url: str,
) -> Job:
    return Job(
        source=source,
        job_id=job_id or str(abs(hash(title + company)))[:10],
        title=title,
        company=company,
        location=location,
        experience=experience,
        salary=salary,
        posted_date="",
        description=description,
        apply_url=apply_url,
        tech_stack=[],
        job_type="",
        industry="",
    )