import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import unicodedata


logger = logging.getLogger(__name__)


@dataclass
class ReviewRecord:
    store: str
    app_id: str
    app_name: Optional[str]
    review_id: str
    user_name: Optional[str]
    rating: Optional[int]
    title: str
    body: str
    language: Optional[str]
    country: Optional[str]
    version: Optional[str]
    created_at: Optional[str]
    fetched_at: str
    extra: Dict[str, Any] = field(default_factory=dict)


def now_utc_iso() -> str:
    """
    Current UTC time in ISO8601 format with timezone info.
    """
    return datetime.now(timezone.utc).isoformat()


def ensure_isoformat(value: Any) -> Optional[str]:
    """
    Convert datetimes or ISO-like strings to ISO8601 UTC strings when possible.
    Falls back to the original string representation if parsing fails.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            logger.debug("Failed to parse datetime string: %s", value)
            return value

    return str(value)


def to_serializable(record: ReviewRecord) -> Dict[str, Any]:
    """
    Convert ReviewRecord to a JSON-serializable dict.
    """
    return asdict(record)


def normalize_app_name(name: Optional[str]) -> Optional[str]:
    """
    Normalize app name to lowercase ASCII (best effort) and hyphen-separated tokens.
    Intended for stable filenames and downstream processing.
    """
    if not name:
        return None
    # Strip accents and drop non-ASCII
    normalized = unicodedata.normalize("NFKD", name)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    # Lowercase and replace non-alphanumeric with hyphen
    cleaned = []
    for ch in normalized:
        if ch.isalnum():
            cleaned.append(ch.lower())
        else:
            cleaned.append("-")
    slug = "".join(cleaned)
    # Collapse multiple hyphens
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    if not slug:
        return None
    primary = slug.split("-")[0] or slug
    return primary


def normalize_user_app_name(name: Optional[str]) -> Optional[str]:
    """
    Normalize user-provided app name; simpler than lookup name.
    Lowercase ASCII, replace non-alnum with hyphen, collapse dashes.
    """
    return normalize_app_name(name)
