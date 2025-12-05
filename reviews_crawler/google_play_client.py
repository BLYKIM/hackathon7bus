import logging
from typing import Iterable, Optional

from .models import ReviewRecord, ensure_isoformat, now_utc_iso


logger = logging.getLogger(__name__)


def _safe_int(value: Optional[int]) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def fetch_google_play_reviews(
    app_id: str,
    country: str = "us",
    max_pages: int = 1,
    page_size: int = 100,
    app_name: Optional[str] = None,
) -> Iterable[ReviewRecord]:
    """
    Fetch public Google Play reviews using google-play-scraper.

    Yields:
        ReviewRecord objects mapped from the scraper output.
    """
    try:
        from google_play_scraper import Sort, reviews
    except ImportError as exc:
        logger.error(
            "google-play-scraper is required for Google Play crawling. Install via pip. Error: %s",
            exc,
        )
        raise SystemExit(1)

    country_lower = country.lower()
    lang = _lang_from_country(country_lower)
    resolved_app_name = app_name
    if resolved_app_name is None:
        try:
            from google_play_scraper import app as app_detail

            info = app_detail(app_id, lang=lang, country=country_lower)
            resolved_app_name = info.get("title")
        except Exception as exc:  # pragma: no cover - best effort only
            logger.debug("Failed to fetch app details for name: %s", exc)

    fetched_at = now_utc_iso()
    continuation_token = None

    for page in range(max_pages):
        logger.info(
            "Fetching Google Play reviews page=%s app_id=%s country=%s",
            page + 1,
            app_id,
            country_lower,
        )
        try:
            result, continuation_token = reviews(
                app_id,
                lang=lang,
                country=country_lower,
                sort=Sort.NEWEST,
                count=page_size,
                continuation_token=continuation_token,
            )
        except Exception as exc:  # pragma: no cover - defensive against network/lib errors
            logger.warning("Failed to fetch Google Play page %s: %s", page + 1, exc)
            break

        if not result:
            logger.info("No reviews returned for Google Play page=%s", page + 1)
            break

        for item in result:
            review_id = item.get("reviewId") or f"{app_id}-{item.get('userName','')}-{item.get('at') or page}"
            title = item.get("title") or ""
            body = item.get("content") or ""
            record = ReviewRecord(
                store="google-play",
                app_id=app_id,
                app_name=resolved_app_name,
                review_id=str(review_id),
                user_name=item.get("userName"),
                rating=_safe_int(item.get("score")),
                title=title,
                body=body,
                language=item.get("userLanguage"),
                country=country_upper(country),
                version=item.get("appVersion") or item.get("reviewCreatedVersion"),
                created_at=ensure_isoformat(item.get("at")),
                fetched_at=fetched_at,
                extra={"thumbs_up": _safe_int(item.get("thumbsUpCount"))},
            )
            yield record

        if not continuation_token:
            logger.info("No continuation token returned; stopping after page=%s", page + 1)
            break


def country_upper(value: str) -> Optional[str]:
    return value.upper() if value else None


def _lang_from_country(country: str) -> str:
    """
    Google Play 스크레이퍼는 lang에 언어코드('en','ko')를 기대한다.
    국가코드와 언어코드를 단순 매핑, 기본값은 'en'.
    """
    mapping = {
        "kr": "ko",
        "us": "en",
        "gb": "en",
        "uk": "en",
        "jp": "ja",
        "tw": "zh",
        "cn": "zh",
        "fr": "fr",
        "de": "de",
        "es": "es",
        "ru": "ru",
        "br": "pt",
        "pt": "pt",
        "it": "it",
        "tr": "tr",
        "id": "id",
    }
    return mapping.get(country, "en")
