#!/usr/bin/env python3
"""
Test case for scraper event loop issue.
"""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from models.search_config import SearchConfig
from models.site_config import SiteConfig
from services.scrapers.generic_scraper import GenericConfigScraper


class TestScraperEventLoop(unittest.TestCase):
    def setUp(self):
        self.config = SearchConfig(
            keywords="python developer",
            locations=["bangalore"],
            sources=["naukri"],
            playwright_enabled=True,
            playwright_headless=True,
            playwright_storage_state_path=""
        )
        self.site = SiteConfig(
            name="naukri",
            strategy="playwright_html",
            bootstrap_url="https://www.naukri.com/",
            search_url="https://www.naukri.com/{{keywords}}-jobs-in-{{locations}}"
        )

    @patch('services.scrapers.generic_scraper.sync_playwright')
    @patch('os.path.exists', return_value=False)
    def test_no_event_loop_error(self, mock_exists, mock_sync_playwright):
        # Mock playwright to avoid actual browser launch
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_page.content.return_value = "<html><body>No jobs</body></html>"
        mock_context.new_page.return_value = mock_page
        mock_browser.new_context.return_value = mock_context
        mock_p.chromium.launch.return_value = mock_browser
        mock_sync_playwright.return_value.__enter__.return_value = mock_p
        mock_sync_playwright.return_value.__exit__.return_value = None

        scraper = GenericConfigScraper(self.config, self.site)

        # This should not raise Event loop is closed error
        try:
            jobs = scraper.fetch_jobs()
            self.assertIsInstance(jobs, list)
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                self.fail("Event loop error occurred")
            else:
                raise

if __name__ == '__main__':
    unittest.main()