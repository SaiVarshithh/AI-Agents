#!/usr/bin/env python3
"""
Worker script for scraping in separate process.
Must be run from the project root directory.
"""

import json
import sys
import os
import logging

# ─── Ensure project root is on sys.path ────────────────────────────────────
# scrape_worker.py lives at project root; __file__ gives us the absolute path.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Set up logging to stderr so stdout stays clean for JSON output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)

from models.search_config import SearchConfig
from models.site_config import SiteConfig
from services.scrapers.generic_scraper import GenericConfigScraper
from services.scrapers.llm_scraper import LLMPoweredScraper

if __name__ == "__main__":
    logger.info("Starting scrape worker")
    if len(sys.argv) != 3:
        logger.error("Usage: python scrape_worker.py <config_json> <site_json>")
        print(json.dumps({"error": "Usage: python scrape_worker.py <config_json> <site_json>"}),
              file=sys.stderr)
        sys.exit(1)

    try:
        config_data = json.loads(sys.argv[1])
        site_data = json.loads(sys.argv[2])
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse arguments: {e}")
        print(json.dumps({"error": f"JSON parse error: {e}"}), file=sys.stderr)
        sys.exit(1)

    logger.info(f"Scraping site: {site_data.get('name')}")
    logger.info(f"Keywords: {config_data.get('keywords')}")
    logger.info(f"Locations: {config_data.get('locations')}")

    config = SearchConfig(**config_data)
    site = SiteConfig(**site_data)

    if site.name.lower() == "llm":
        scraper = LLMPoweredScraper(config)
    else:
        scraper = GenericConfigScraper(config, site)

    try:
        logger.info("Fetching jobs...")
        jobs = scraper.fetch_jobs()
        logger.info(f"Successfully fetched {len(jobs)} jobs")
        # Output ONLY the JSON result to stdout — controller reads this
        print(json.dumps([j.__dict__ for j in jobs]))
    except Exception as e:
        logger.error(f"Error fetching jobs: {e}", exc_info=True)
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)