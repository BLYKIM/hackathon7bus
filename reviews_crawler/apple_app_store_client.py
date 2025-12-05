import logging
from typing import Iterable, Optional

from .models import ReviewRecord, ensure_isoformat, now_utc_iso
from .google_play_client import country_upper


logger = logging.getLogger(__name__)


def _safe_int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def fetch_app_store_reviews(
    app_id: str,
    country: str = "us",
    max_pages: int = 1,
    app_name: Optional[str] = None,
) -> Iterable[ReviewRecord]:
    """
    Fetch public Apple App Store reviews via the iTunes RSS JSON feed.

    Yields:
        ReviewRecord objects mapped from feed entries.
    """
    try:
        import requests  # type: ignore
    except ImportError:
        logger.error(
            "requests 가 필요합니다. 'python -m pip install requests' 실행하거나 --install-missing 옵션을 사용하세요."
        )
        raise SystemExit(1)

    country_lower = country.lower()
    fetched_at = now_utc_iso()

    for page in range(1, max_pages + 1):
        url = (
            f"https://itunes.apple.com/{country_lower}/rss/customerreviews/"
            f"page={page}/id={app_id}/sortby=mostrecent/json"
        )
        logger.info("Fetching App Store reviews page=%s app_id=%s country=%s", page, app_id, country_lower)
        try:
            response = requests.get(url, timeout=10)
        except requests.RequestException as exc:
            logger.warning("Request failed for App Store page=%s: %s", page, exc)
            break

        if response.status_code != 200:
            logger.warning(
                "Unexpected status for App Store page=%s: %s", page, response.status_code
            )
            break

        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("Failed to parse JSON for App Store page=%s: %s", page, exc)
            break

        entries = payload.get("feed", {}).get("entry", []) or []
        review_entries = [entry for entry in entries if "im:rating" in entry]

        if not review_entries:
            logger.info("No review entries found for App Store page=%s", page)
            break

        for idx, entry in enumerate(review_entries):
            record = ReviewRecord(
                store="app-store",
                app_id=app_id,
                app_name=app_name,
                review_id=_get_label(entry.get("id")) or f"{app_id}-{page}-{idx}",
                user_name=_get_label(entry.get("author", {}).get("name")),
                rating=_safe_int(_get_label(entry.get("im:rating"))),
                title=_get_label(entry.get("title")) or "",
                body=_get_label(entry.get("content")) or _get_label(entry.get("summary")) or "",
                language=_get_label(entry.get("content", {}).get("attributes", {}).get("lang")),
                country=country_upper(country),
                version=_get_label(entry.get("im:version")),
                created_at=ensure_isoformat(
                    _get_label(entry.get("updated")) or _get_label(entry.get("im:releaseDate"))
                ),
                fetched_at=fetched_at,
                extra={"vote_sum": _safe_int(_get_label(entry.get("im:voteSum")))},
            )
            yield record


def _get_label(node: Optional[dict]) -> Optional[str]:
    if isinstance(node, dict):
        return node.get("label")
    return None
