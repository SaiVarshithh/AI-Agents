from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from playwright.sync_api import sync_playwright

from config.settings import settings
from models.search_config import SearchConfig


class PlaywrightFetcher:
    """
    Minimal Playwright wrapper:
    - Creates a browser context with optional storage_state (cookies/session)
    - Performs HTTP requests through the browser context (often more accepted than raw requests)
    - Can open a page for manual login/captcha if needed
    """

    def __init__(self, config: SearchConfig):
        self.config = config
        self._ensure_windows_event_loop_policy()

    def _ensure_windows_event_loop_policy(self) -> None:
        """
        Playwright launches a driver subprocess.
        On Windows, SelectorEventLoop can raise NotImplementedError for subprocess APIs.
        Force Proactor policy to avoid:
          NotImplementedError at asyncio.create_subprocess_exec(...)
        """
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
            # Non-fatal; normal error handling in request_json will surface details.
            pass

    def request_json(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        timeout_ms: int = 30000,
        ensure_json: bool = True,
    ) -> Any:
        method = (method or "GET").upper()
        headers = headers or {}
        params = params or {}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=bool(self.config.playwright_headless))
            ctx_kwargs: dict[str, Any] = {}
            if self.config.playwright_storage_state_path and os.path.exists(self.config.playwright_storage_state_path):
                ctx_kwargs["storage_state"] = self.config.playwright_storage_state_path
            context = browser.new_context(**ctx_kwargs)
            try:
                req = context.request
                resp = req.fetch(
                    url,
                    method=method,
                    headers=headers,
                    params={k: str(v) for k, v in params.items() if v is not None},
                    data=json.dumps(json_body).encode("utf-8") if json_body is not None else None,
                    timeout=timeout_ms,
                )
                status = resp.status
                if status >= 400:
                    body = (resp.text() or "").strip().replace("\n", " ")[:200]
                    raise RuntimeError(f"HTTP {status}. Body: {body}")
                if ensure_json:
                    ctype = (resp.headers.get("content-type") or "").lower()
                    if "json" not in ctype:
                        body = (resp.text() or "").strip().replace("\n", " ")[:200]
                        raise RuntimeError(f"Expected JSON but got '{ctype or 'unknown'}'. Body: {body}")
                return resp.json()
            finally:
                context.close()
                browser.close()

    def manual_session_bootstrap(self, url: str) -> str:
        """
        Opens a real browser window for the user to login/solve captcha,
        then saves storage state and returns the saved file path.
        """
        out_dir = settings.OUTPUT_DIR
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "storage_state.json")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            # User does the login/captcha in the opened window.
            page.wait_for_timeout(15000)
            context.storage_state(path=out_path)
            context.close()
            browser.close()
        return out_path

