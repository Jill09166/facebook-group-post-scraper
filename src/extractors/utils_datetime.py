import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from dateutil import parser as dateutil_parser

def parse_facebook_datetime(raw: str) -> Optional[int]:
    """
    Best-effort parser that converts various Facebook-like datetime formats
    into a Unix timestamp (seconds since epoch, UTC).

    Supported patterns include:
    - Unix timestamps as strings (e.g., "1715352299")
    - ISO8601 or human-readable dates (via dateutil)
    - Relative times like "3 h", "2 hrs", "5 d", "1 w"
    - The special keyword "now"

    Returns None if parsing fails.
    """
    if not raw:
        return None

    text = raw.strip().lower()

    if text == "now":
        return int(time.time())

    # If raw looks like a pure integer, treat it as Unix timestamp
    if re.fullmatch(r"\d{9,12}", text):
        try:
            ts = int(text)
            # Assume seconds; if it looks like ms, convert
            if ts > 10_000_000_000:
                ts = ts // 1000
            return ts
        except ValueError:
            pass

    # Relative times like "2 h", "3 hrs", "5 d", "1 w"
    rel_match = re.search(r"(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|week|weeks)", text)
    if rel_match:
        amount = int(rel_match.group(1))
        unit = rel_match.group(2)

        delta = None
        if unit.startswith("s"):
            delta = timedelta(seconds=amount)
        elif unit.startswith("m"):
            delta = timedelta(minutes=amount)
        elif unit.startswith("h"):
            delta = timedelta(hours=amount)
        elif unit.startswith("d"):
            delta = timedelta(days=amount)
        elif unit.startswith("w"):
            delta = timedelta(weeks=amount)

        if delta is not None:
            return int((datetime.now(timezone.utc) - delta).timestamp())

    # Try parsing as a full date string using dateutil
    try:
        dt = dateutil_parser.parse(raw)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, OverflowError):
        pass

    # If everything fails, return None
    return None