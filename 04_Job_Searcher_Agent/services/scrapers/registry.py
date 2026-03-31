from __future__ import annotations

import json
import os
from typing import Iterable

from config.settings import settings
from models.site_config import SiteConfig


class SiteRegistry:
    """
    Loads site definitions from `config/sites/*.json`.

    This is what makes sources dynamic: adding a new site should only require
    adding a new JSON config file (no Python code edits).
    """

    def __init__(self, sites_dir: str | None = None):
        self.sites_dir = sites_dir or settings.SITES_DIR

    def list_site_configs(self) -> list[SiteConfig]:
        if not os.path.isdir(self.sites_dir):
            return []

        configs: list[SiteConfig] = []
        for fname in sorted(os.listdir(self.sites_dir)):
            if not fname.lower().endswith(".json"):
                continue
            path = os.path.join(self.sites_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                cfg = SiteConfig(**raw)
                if cfg.enabled:
                    configs.append(cfg)
            except Exception as e:
                print(f"[SiteRegistry] Failed loading {path}: {e}")
        return configs

    def supported_source_names(self) -> list[str]:
        return [c.name for c in self.list_site_configs()]

