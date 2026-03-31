from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional


import urllib.parse

def build_template_context(config, site=None) -> dict[str, Any]:
    """Build template substitution context from search config.
    
    The optional `site` param is accepted but unused — kept for
    backward compatibility with older callers that pass (config, site).
    """
    locations_csv = ",".join(config.locations) if getattr(config, "locations", None) else ""
    # For URL paths, use hyphen-joined keywords and first location
    keywords_raw = getattr(config, "keywords", "") or ""
    keywords_slug = keywords_raw.replace(" ", "-").replace(",", "-").lower()
    locations_slug = config.locations[0].replace(" ", "-").lower() if getattr(config, "locations", None) else ""
    locations_joined = " ".join(config.locations) if getattr(config, "locations", None) else ""
    return {
        "keywords": keywords_raw,
        "keywords_url": urllib.parse.quote_plus(keywords_raw),
        "keywords_slug": keywords_slug,
        "locations_csv": locations_csv,
        "locations": locations_joined,
        "locations_url": urllib.parse.quote_plus(locations_joined),
        "locations_csv_url": urllib.parse.quote_plus(locations_csv),
        "locations_slug": locations_slug,
        "job_age_days": getattr(config, "job_age_days", 7),
        "max_results_per_source": min(int(getattr(config, "max_results_per_source", 25) or 25), 50),
    }


_tmpl_re = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def render_templates(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {k: render_templates(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [render_templates(v, context) for v in value]
    if not isinstance(value, str):
        return value

    def repl(m: re.Match) -> str:
        key = m.group(1)
        v = context.get(key, "")
        return str(v if v is not None else "")

    return _tmpl_re.sub(repl, value)


def apply_transform(name: str, value: Any, *, source: str = "", full_item: Any = None) -> Any:
    name = (name or "").strip()
    if not name:
        return value

    if name == "csv_to_list":
        if not value:
            return []
        if isinstance(value, str):
            return [t.strip() for t in value.split(",") if t.strip()]
        return value

    if name == "list_clean":
        if not isinstance(value, list):
            return []
        out = []
        for v in value:
            s = str(v or "").strip()
            if s:
                out.append(s)
        return out

    if name == "iso_to_ymd":
        if not value:
            return ""
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return str(value)

    if name == "naukri_epoch_ms_to_ymd":
        if not value:
            return ""
        try:
            ts = int(value) / 1000
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        except Exception:
            return str(value)

    if name == "naukri_jdurl_to_absolute":
        if not value:
            return ""
        s = str(value)
        if s.startswith("/"):
            return f"https://www.naukri.com{s}"
        return s

    if name == "monster_jobid_to_url":
        if not value:
            return ""
        job_id = str(value).strip()
        return f"https://www.foundit.in/job/details/{job_id}"

    if name == "monster_exp_range":
        # input is experienceMin; we also map experience_max separately and the scraper
        # combines if both are numeric. Keep value as-is.
        return value

    return value
