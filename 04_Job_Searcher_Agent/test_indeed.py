from models.search_config import SearchConfig
from models.site_config import SiteConfig
from services.scrapers.generic_scraper import GenericConfigScraper
import json

# Load indeed config
with open('config/sites/indeed.json', 'r') as f:
    site_data = json.load(f)

site = SiteConfig(**site_data)

config = SearchConfig(
    keywords="python developer remote",
    locations=["India"],
    sources=["indeed"],
    playwright_enabled=True,
    playwright_headless=True,
    max_results_per_source=5
)

scraper = GenericConfigScraper(config, site)
jobs = scraper.fetch_jobs()

print(f"Found {len(jobs)} jobs")
for job in jobs:
    print(f"{job.title} | {job.company} | {job.location}")