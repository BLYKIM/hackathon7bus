"""
Lightweight review crawler package for Google Play and Apple App Store.
"""

from .models import ReviewRecord, ensure_isoformat, now_utc_iso, to_serializable
from .google_play_client import fetch_google_play_reviews
from .apple_app_store_client import fetch_app_store_reviews
from .deps import ensure_dependencies

__all__ = [
    "ReviewRecord",
    "ensure_isoformat",
    "now_utc_iso",
    "to_serializable",
    "fetch_google_play_reviews",
    "fetch_app_store_reviews",
    "ensure_dependencies",
]
