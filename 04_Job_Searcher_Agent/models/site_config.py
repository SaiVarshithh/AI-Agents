from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SiteConfig:
    """
    Config-driven site definition.

    Add a new website by dropping a new JSON file into `config/sites/`.
    """

    name: str
    label: str = ""
    enabled: bool = True
    strategy: str = "http_json"  # http_json | http_json_paged | http_html (future)

    bootstrap_url: Optional[str] = None
    search_url: Optional[str] = None

    request: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    paging: dict[str, Any] = field(default_factory=dict)

    mappings: dict[str, str] = field(default_factory=dict)
    transforms: dict[str, str] = field(default_factory=dict)

    def display_name(self) -> str:
        return self.label or self.name

