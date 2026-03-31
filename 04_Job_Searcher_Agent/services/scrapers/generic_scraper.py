from __future__ import annotations

import os
import re
import sys
import time
import asyncio
import logging
from typing import Any, List

import jmespath
import requests
from bs4 import BeautifulSoup

from config.settings import settings
from models.job import Job
from models.search_config import SearchConfig
from models.site_config import SiteConfig
from utils.site_transforms import (
    apply_transform,
    build_template_context,
    render_templates,
)
from .base_scraper import BaseScraper
from .playwright_fetcher import PlaywrightFetcher
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


class GenericConfigScraper(BaseScraper):
    """
    Scraper driven by SiteConfig.

    Supports:
    - JSON response parsing using JMESPath expressions with optional paging (http_json / http_json_paged)
    - Playwright-based HTML scraping for anti-bot protected sites (playwright_html)
    - Playwright-based JSON API interception (playwright_json / playwright_json_paged)
    """

    def __init__(self, config: SearchConfig, site: SiteConfig):
        super().__init__(config)
        self.site = site

    @property
    def SOURCE_NAME(self) -> str:  # type: ignore[override]
        return self.site.name

    # ─── Entry point ──────────────────────────────────────────────────────────

    def fetch_jobs(self) -> List[Job]:
        logger.info(f"Starting fetch_jobs for {self.site.name}")
        strategy = (self.site.strategy or "http_json").lower()
        logger.info(f"Using strategy: {strategy}")

        if strategy == "http_json":
            return self._fetch_json_single()
        if strategy == "http_json_paged":
            return self._fetch_json_paged()
        if strategy == "playwright_json":
            return self._fetch_playwright_json(single=True)
        if strategy == "playwright_json_paged":
            return self._fetch_playwright_json(single=False)
        if strategy == "playwright_html":
            return self._fetch_playwright_html()
        if strategy == "playwright_intercept":
            return self._fetch_playwright_intercept()

        logger.error(f"Unsupported strategy: {self.site.strategy}")
        raise ValueError(f"Unsupported strategy: {self.site.strategy}")

    # ─── HTTP JSON strategies ─────────────────────────────────────────────────

    def _fetch_json_single(self) -> List[Job]:
        payload = self._request_payload()
        data = self._request_json(payload)
        return self._parse_json_items(data)

    def _fetch_json_paged(self) -> List[Job]:
        paging = self.site.paging or {}
        mode = (paging.get("mode") or "").lower()
        if mode != "offset_rows":
            raise ValueError(f"Unsupported paging mode: {mode}")

        rows_param = paging.get("rows_param", "noOfResults")
        start_param = paging.get("start_param", "start")
        page_size = int(paging.get("page_size", 25))
        max_pages = int(paging.get("max_pages", 4))

        target = min(self.config.max_results_per_source, 100)
        collected: List[Job] = []

        for page in range(max_pages):
            if len(collected) >= target:
                break
            payload = self._request_payload()
            params = dict(payload.get("params", {}))
            params[start_param] = page * page_size
            params[rows_param] = min(page_size, target - len(collected))
            payload["params"] = params

            try:
                data = self._request_json(payload)
                batch = self._parse_json_items(data)
                if not batch:
                    logger.info(f"No more results at page {page}")
                    break
                collected.extend(batch)
                logger.info(f"Page {page}: got {len(batch)} jobs (total: {len(collected)})")
                if len(batch) < page_size:
                    break
                time.sleep(0.5)   # polite delay between pages
            except Exception as e:
                logger.error(f"Error on page {page}: {e}")
                break

        return collected[:target]

    # ─── Playwright JSON strategies ───────────────────────────────────────────

    def _fetch_playwright_json(self, *, single: bool) -> List[Job]:
        if not self.config.playwright_enabled:
            raise RuntimeError("Playwright is disabled in config")

        self._ensure_windows_event_loop_policy()
        fetcher = PlaywrightFetcher(self.config)

        if single:
            payload = self._request_payload()
            data = self._request_json_playwright(payload, fetcher)
            return self._parse_json_items(data)

        paging = self.site.paging or {}
        mode = (paging.get("mode") or "").lower()
        if mode != "offset_rows":
            raise ValueError(f"Unsupported paging mode: {mode}")

        rows_param = paging.get("rows_param", "rows")
        start_param = paging.get("start_param", "start")
        page_size = int(paging.get("page_size", 25))
        max_pages = int(paging.get("max_pages", 4))

        target = min(self.config.max_results_per_source, 100)
        collected: List[Job] = []

        for page in range(max_pages):
            if len(collected) >= target:
                break
            payload = self._request_payload()
            params = dict(payload.get("params", {}))
            params[start_param] = page * page_size
            params[rows_param] = min(page_size, target - len(collected))
            payload["params"] = params

            data = self._request_json_playwright(payload, fetcher)
            batch = self._parse_json_items(data)
            collected.extend(batch)
            if len(batch) < page_size:
                break

        return collected[:target]

    # ─── Playwright Intercept strategy ───────────────────────────────────────
    # Navigate to the site's own search page; intercept the JSON API call
    # that the page makes internally (authenticated via browser cookies).
    # This bypasses CAPTCHA because we appear as a normal browser user.

    def _fetch_playwright_intercept(self) -> List[Job]:
        """Browse to the search page and intercept the site's own API JSON responses."""
        if not self.site.search_url:
            raise ValueError("search_url not defined for playwright_intercept")

        self._ensure_windows_event_loop_policy()

        intercept_keyword = (self.site.response or {}).get("intercept_url_contains", "")
        items_path = (self.site.response or {}).get("items_path", "")

        template_context = build_template_context(self.config)
        search_url = render_templates(self.site.search_url, template_context)
        logger.info(f"[{self.site.name}] Intercept browse → {search_url}")

        intercepted_data: list = []

        def on_response(resp):
            if resp.status != 200:
                return
            ct = (resp.headers.get("content-type") or "").lower()
            if "json" not in ct:
                return
            if intercept_keyword and intercept_keyword not in resp.url:
                return
            try:
                data = resp.json()
                items = jmespath.search(items_path, data) if items_path else data
                if isinstance(items, list) and items:
                    logger.info(f"[{self.site.name}] Intercepted {len(items)} items from {resp.url[:80]}")
                    intercepted_data.append(data)
                elif not items_path and isinstance(data, list) and data:
                    intercepted_data.append(data)
            except Exception as e:
                logger.debug(f"[{self.site.name}] Intercept parse error: {e}")

        browser = None
        context = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=False,   # must be non-headless — sites detect & block headless
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--window-position=-32000,-32000",  # move off-screen so it's not distracting
                    ],
                )
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1366, "height": 768},
                    locale="en-IN",
                )
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                # Load saved session cookies if available
                state_path = (
                    self.config.playwright_storage_state_path
                    or os.path.join(settings.OUTPUT_DIR, f"{self.site.name}_state.json")
                )
                if os.path.exists(state_path):
                    try:
                        context.storage_state  # verify attr exists
                        context.close()
                        context = browser.new_context(
                            user_agent=(
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/124.0.0.0 Safari/537.36"
                            ),
                            viewport={"width": 1366, "height": 768},
                            locale="en-IN",
                            storage_state=state_path,
                        )
                        context.add_init_script(
                            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                        )
                    except Exception:
                        pass

                page = context.new_page()
                page.on("response", on_response)

                page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                # Wait for API calls to complete
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                page.wait_for_timeout(5000)

                # Save cookies for future runs
                try:
                    os.makedirs(os.path.dirname(state_path) or settings.OUTPUT_DIR, exist_ok=True)
                    context.storage_state(path=state_path)
                except Exception:
                    pass

                # If we got intercepted data, parse it
                if intercepted_data:
                    jobs: List[Job] = []
                    for data in intercepted_data:
                        batch = self._parse_json_items(data)
                        jobs.extend(batch)
                    logger.info(f"[{self.site.name}] Intercept parsed {len(jobs)} jobs")
                    if jobs:
                        return jobs[: self.config.max_results_per_source]

                # Fallback: parse HTML if no API was intercepted
                logger.info(f"[{self.site.name}] No API intercepted, falling back to HTML parsing")
                html = page.content()
                return self._parse_html_jobs(html)
        finally:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass

    # ─── Playwright HTML strategy ─────────────────────────────────────────────

    def _fetch_playwright_html(self) -> List[Job]:
        if not self.config.playwright_enabled:
            raise RuntimeError("Playwright is disabled in config")

        if not self.site.search_url:
            raise ValueError("search_url not defined for HTML scraping")

        self._ensure_windows_event_loop_policy()

        state_path = (
            self.config.playwright_storage_state_path
            or os.path.join(settings.OUTPUT_DIR, "storage_state.json")
        )

        browser = None
        context = None
        try:
            with sync_playwright() as p:
                headless = self.config.playwright_headless
                browser = p.chromium.launch(
                    headless=headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                    ],
                )

                ctx_kwargs: dict = {
                    "user_agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "viewport": {"width": 1280, "height": 800},
                }
                if os.path.exists(state_path):
                    ctx_kwargs["storage_state"] = state_path

                context = browser.new_context(**ctx_kwargs)

                # Hide webdriver flag from JavaScript
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                page = context.new_page()

                # Build search URL
                template_context = build_template_context(self.config)
                search_url = render_templates(self.site.search_url, template_context)
                logger.info(f"Navigating to {search_url}")

                page.goto(search_url, wait_until="domcontentloaded", timeout=45000)

                # Wait for job content to appear
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass  # networkidle may time out on heavy pages — continue anyway
                page.wait_for_timeout(4000)

                html = page.content()
                logger.info(f"Retrieved HTML length: {len(html)}")

                # Save storage state for future runs
                try:
                    os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
                    context.storage_state(path=state_path)
                except Exception:
                    pass

                jobs = self._parse_html_jobs(html)
                logger.info(f"Parsed {len(jobs)} jobs from HTML")
                return jobs
        finally:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass

    # ─── HTML Parsing ─────────────────────────────────────────────────────────

    def _parse_html_jobs(self, html: str) -> List[Job]:
        """Parse job listings from HTML for each supported site."""
        logger.info(f"Parsing HTML jobs for site: {self.site.name}")
        soup = BeautifulSoup(html, "lxml")
        jobs: List[Job] = []

        if self.site.name == "naukri":
            jobs = self._parse_naukri_html(soup)
        elif self.site.name == "monster":
            jobs = self._parse_monster_html(soup)
        elif self.site.name == "indeed":
            jobs = self._parse_indeed_html(soup)
        else:
            logger.warning(f"No HTML parser for site: {self.site.name}")

        logger.info(f"Parsed {len(jobs)} jobs from {self.site.name} HTML")
        return jobs   # ← FIX: was missing this return in original code

    def _parse_naukri_html(self, soup: BeautifulSoup) -> List[Job]:
        """Parse Naukri.com search results HTML (current DOM, 2024+)."""
        jobs: List[Job] = []

        # Naukri uses article tags with class containing 'jobTuple'
        cards = soup.find_all("article", class_=re.compile(r"jobTuple", re.I))
        if not cards:
            # Fallback: try any div/article with data-job-id attribute
            cards = soup.find_all(attrs={"data-job-id": True})
        if not cards:
            # Last resort: find any element with jobId in its id attr
            cards = soup.find_all("div", id=re.compile(r"job-", re.I))

        logger.info(f"Naukri: found {len(cards)} card elements")

        for card in cards[: self.config.max_results_per_source]:
            try:
                # Title — the main anchor with job link
                title_el = (
                    card.find("a", class_=re.compile(r"title", re.I))
                    or card.find("a", attrs={"title": True})
                    or card.find("h2")
                )
                title = self._safe_strip(title_el.get_text()) if title_el else ""
                apply_url = title_el.get("href", "") if title_el else ""
                if apply_url.startswith("/"):
                    apply_url = f"https://www.naukri.com{apply_url}"

                # Company
                company_el = (
                    card.find("a", class_=re.compile(r"comp", re.I))
                    or card.find("span", class_=re.compile(r"comp", re.I))
                )
                company = self._safe_strip(company_el.get_text()) if company_el else ""

                # Location
                loc_el = (
                    card.find("span", class_=re.compile(r"loc|location", re.I))
                    or card.find("li", class_=re.compile(r"loc|location", re.I))
                )
                location = self._safe_strip(loc_el.get_text()) if loc_el else ""

                # Experience
                exp_el = card.find("span", class_=re.compile(r"exp", re.I))
                experience = self._safe_strip(exp_el.get_text()) if exp_el else ""

                # Salary
                sal_el = card.find("span", class_=re.compile(r"sal", re.I))
                salary = self._safe_strip(sal_el.get_text()) if sal_el else ""

                # Posted date
                posted_el = card.find("span", class_=re.compile(r"posted|date|day", re.I))
                posted_date = self._safe_strip(posted_el.get_text()) if posted_el else ""

                # Job ID from URL
                job_id = apply_url.split("?")[0].rstrip("/").split("-")[-1] if apply_url else ""

                if not title:
                    continue

                jobs.append(Job(
                    source=self.site.name,
                    job_id=job_id,
                    title=title,
                    company=company,
                    location=location,
                    experience=experience,
                    salary=salary,
                    posted_date=posted_date,
                    description="",
                    apply_url=apply_url,
                    tech_stack=[],
                    job_type="",
                    industry="",
                ))
            except Exception as e:
                logger.debug(f"Naukri card parse error: {e}")
                continue

        return jobs

    def _parse_monster_html(self, soup: BeautifulSoup) -> List[Job]:
        """Parse foundit.in (Monster India) search results HTML."""
        jobs: List[Job] = []

        # Foundit.in uses cards with class containing 'card-apply-content' or 'srpResultCardContainer'
        cards = soup.find_all("div", class_=re.compile(r"card-apply-content|srpResultCard|jobTuple", re.I))
        if not cards:
            cards = soup.find_all("div", attrs={"data-job-id": True})
        if not cards:
            # Try generic job card patterns
            cards = soup.find_all("div", class_=re.compile(r"job.?card|result.?card|listing", re.I))

        logger.info(f"Monster: found {len(cards)} card elements")

        for card in cards[: self.config.max_results_per_source]:
            try:
                # Title
                title_el = (
                    card.find("a", class_=re.compile(r"job.?title|title", re.I))
                    or card.find("h3")
                    or card.find("h2")
                )
                if not title_el:
                    # fallback: any anchor with href + text
                    title_el = card.find("a", href=True)
                title = self._safe_strip(title_el.get_text()) if title_el else ""
                apply_url = title_el.get("href", "") if title_el else ""
                if apply_url.startswith("/"):
                    apply_url = f"https://www.foundit.in{apply_url}"

                # Company
                company_el = (
                    card.find("span", class_=re.compile(r"company|employer", re.I))
                    or card.find("a", class_=re.compile(r"company", re.I))
                )
                company = self._safe_strip(company_el.get_text()) if company_el else ""

                # Location
                loc_el = card.find(class_=re.compile(r"location|loc", re.I))
                location = self._safe_strip(loc_el.get_text()) if loc_el else ""

                # Experience
                exp_el = card.find(class_=re.compile(r"exp", re.I))
                experience = self._safe_strip(exp_el.get_text()) if exp_el else ""

                # Salary
                sal_el = card.find(class_=re.compile(r"sal|ctc|salary", re.I))
                salary = self._safe_strip(sal_el.get_text()) if sal_el else ""

                # Date
                date_el = card.find(class_=re.compile(r"date|posted|ago", re.I))
                posted_date = self._safe_strip(date_el.get_text()) if date_el else ""

                # Job ID from data attribute or URL
                job_id = (
                    card.get("data-job-id", "")
                    or (apply_url.split("?")[0].rstrip("/").split("/")[-1] if apply_url else "")
                )

                if not title:
                    continue

                jobs.append(Job(
                    source=self.site.name,
                    job_id=str(job_id),
                    title=title,
                    company=company,
                    location=location,
                    experience=experience,
                    salary=salary,
                    posted_date=posted_date,
                    description="",
                    apply_url=apply_url,
                    tech_stack=[],
                    job_type="",
                    industry="",
                ))
            except Exception as e:
                logger.debug(f"Monster card parse error: {e}")
                continue

        return jobs

    def _parse_indeed_html(self, soup: BeautifulSoup) -> List[Job]:
        """Parse Indeed search results HTML."""
        jobs: List[Job] = []
        cards = soup.find_all("div", class_="job_seen_beacon")
        logger.info(f"Indeed: found {len(cards)} card elements")

        for card in cards[: self.config.max_results_per_source]:
            try:
                title_el = card.find("span", id=lambda x: x and x.startswith("jobTitle"))
                if not title_el:
                    continue
                title = self._safe_strip(title_el.get_text())
                company_el = card.find(attrs={"data-testid": "company-name"})
                company = self._safe_strip(company_el.get_text()) if company_el else ""
                location_el = card.find(attrs={"data-testid": "text-location"})
                location = self._safe_strip(location_el.get_text()) if location_el else ""
                link_el = card.find("a", href=True)
                apply_url = link_el["href"] if link_el else ""
                if apply_url.startswith("/"):
                    apply_url = f"https://www.indeed.com{apply_url}"
                job_id = apply_url.split("?")[0].split("/")[-1] if apply_url else ""
                jobs.append(Job(
                    source=self.site.name,
                    job_id=job_id,
                    title=title,
                    company=company,
                    location=location,
                    salary="",
                    posted_date="",
                    description="",
                    apply_url=apply_url,
                    tech_stack=[],
                    job_type="",
                    industry="",
                    experience="",
                ))
            except Exception as e:
                logger.debug(f"Indeed card parse error: {e}")
                continue
        return jobs

    # ─── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_strip(text: str) -> str:
        return " ".join((text or "").split()).strip()

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

    def _request_json_playwright(self, req: dict[str, Any], fetcher: PlaywrightFetcher) -> Any:
        timeout_ms = int(
            1000 * int(getattr(settings, req.get("timeout_setting", "REQUEST_TIMEOUT"),
                               settings.REQUEST_TIMEOUT))
        )
        return fetcher.request_json(
            method=req.get("method", "GET"),
            url=req.get("url", ""),
            headers=req.get("headers", {}),
            params=req.get("params", {}),
            json_body=req.get("json") if req.get("method", "GET") != "GET" else None,
            timeout_ms=timeout_ms,
            ensure_json=True,
        )

    def _request_payload(self) -> dict[str, Any]:
        # FIX: build_template_context accepts (config) or (config, site) — both work now
        ctx = build_template_context(self.config)
        req = dict(self.site.request or {})

        params = dict(req.get("params", {}) or {})
        req["params"] = render_templates(params, ctx)

        url = req.get("url", "")
        req["url"] = render_templates(url, ctx)

        # headers may come from settings to avoid duplicating in JSON
        headers = dict(req.get("headers", {}) or {})
        hdr_key = req.get("headers_from_settings")
        if hdr_key:
            headers.update(getattr(settings, hdr_key, {}) or {})
        req["headers"] = headers

        req["method"] = (req.get("method") or "GET").upper()
        return req

    def _request_json(self, req: dict[str, Any]) -> Any:
        method = req.get("method", "GET")
        url = req.get("url")
        headers = req.get("headers", {})
        params = req.get("params", {})
        timeout = int(getattr(settings, req.get("timeout_setting", "REQUEST_TIMEOUT"),
                              settings.REQUEST_TIMEOUT))

        for attempt in range(settings.MAX_RETRIES):
            try:
                r = requests.request(
                    method,
                    url,
                    headers=headers,
                    params={k: str(v) for k, v in params.items() if v is not None} if method == "GET" else None,
                    json=req.get("json") if method != "GET" else None,
                    timeout=timeout,
                )
                if r.status_code >= 400:
                    snippet = (r.text or "").strip().replace("\n", " ")[:300]
                    raise RuntimeError(f"HTTP {r.status_code} {r.reason}. Body: {snippet}")
                ctype = (r.headers.get("Content-Type") or "").lower()
                if "json" not in ctype:
                    snippet = (r.text or "").strip().replace("\n", " ")[:300]
                    raise RuntimeError(f"Expected JSON but got '{ctype or 'unknown'}'. Body: {snippet}")
                return r.json()
            except requests.RequestException as e:
                if attempt < settings.MAX_RETRIES - 1:
                    time.sleep(settings.RETRY_DELAY * (attempt + 1))
                    continue
                raise RuntimeError(f"{self.site.name} request failed: {e}") from e
            except RuntimeError:
                if attempt < settings.MAX_RETRIES - 1:
                    time.sleep(settings.RETRY_DELAY * (attempt + 1))
                    continue
                raise

    def _parse_json_items(self, data: Any) -> List[Job]:
        items_path = (self.site.response or {}).get("items_path", "")
        items = jmespath.search(items_path, data) if items_path else data
        if not isinstance(items, list):
            logger.warning(f"Expected list from items_path '{items_path}', got {type(items).__name__}")
            return []

        jobs: List[Job] = []
        for item in items:
            try:
                mapped = self._map_item(item)
                job = self._to_job(mapped)
                if job.title:  # skip empty jobs
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"[{self.site.name}] Parse error: {e}")
        return jobs

    def _map_item(self, item: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for field, expr in (self.site.mappings or {}).items():
            if not expr:
                continue
            out[field] = jmespath.search(expr, item)
        for field, tname in (self.site.transforms or {}).items():
            if field in out:
                out[field] = apply_transform(tname, out[field], source=self.site.name, full_item=item)
        return out

    def _to_job(self, mapped: dict[str, Any]) -> Job:
        posted_date = mapped.get("posted_date") or ""
        tech_stack = mapped.get("tech_stack") or []
        if isinstance(tech_stack, str):
            tech_stack = [t.strip() for t in tech_stack.split(",") if t.strip()]

        exp = mapped.get("experience")
        exp_max = mapped.get("experience_max")
        if (exp is not None and exp_max is not None
                and isinstance(exp, (int, float))
                and isinstance(exp_max, (int, float))):
            exp = f"{int(exp)} - {int(exp_max)} yrs"

        apply_url = mapped.get("apply_url") or ""

        return Job(
            title=str(mapped.get("title") or "").strip(),
            company=str(mapped.get("company") or "").strip(),
            location=str(mapped.get("location") or "").strip(),
            experience=str(exp or "").strip(),
            salary=str(mapped.get("salary") or "").strip(),
            posted_date=str(posted_date or "").strip(),
            apply_url=str(apply_url or "").strip(),
            description=str(mapped.get("description") or "").strip(),
            tech_stack=list(tech_stack) if isinstance(tech_stack, list) else [],
            source=self.site.name,
            job_id=str(mapped.get("job_id") or "").strip(),
            job_type=str(mapped.get("job_type") or "").strip(),
            industry=str(mapped.get("industry") or "").strip(),
        )
