import re
from datetime import datetime, timedelta


def parse_naukri_date(raw: str) -> str:
    """Parse Naukri's epoch ms or string date into readable format."""
    if not raw:
        return ""
    try:
        # Naukri returns epoch milliseconds as string
        ts = int(raw) / 1000
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return str(raw)


def parse_monster_date(raw: str) -> str:
    """Parse Monster India's ISO date string."""
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return str(raw)


def sanitize_filename(name: str) -> str:
    """Remove characters unsafe for filenames."""
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def format_ctc_range(min_ctc, max_ctc) -> str:
    parts = []
    if min_ctc is not None:
        parts.append(f"{min_ctc} LPA")
    if max_ctc is not None:
        parts.append(f"{max_ctc} LPA")
    if len(parts) == 2:
        return f"{parts[0]} - {parts[1]}"
    return parts[0] if parts else ""