from __future__ import annotations

from datetime import datetime, timedelta


def parse_ymd(value: str) -> datetime | None:
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def is_within_days(ymd: str, days: int) -> bool:
    dt = parse_ymd(ymd)
    if not dt:
        return True  # if we can't parse, don't exclude
    cutoff = datetime.now() - timedelta(days=int(days))
    return dt >= cutoff

