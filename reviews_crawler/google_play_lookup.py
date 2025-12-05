import logging
from typing import Optional, Tuple


logger = logging.getLogger(__name__)


def lookup_google_play_by_name(app_name: str, country: str = "us", lang: str | None = None) -> Optional[Tuple[str, str]]:
    """
    Search Google Play by app name. Returns (app_id, app_name) if found.
    """
    try:
        from google_play_scraper import search
    except ImportError:
        logger.error("google-play-scraper 패키지가 필요합니다. --install-missing 옵션을 사용하거나 pip로 설치하세요.")
        return None

    lang_code = lang or country.lower()
    country_lower = country.lower()
    try:
        results = search(app_name, lang=lang_code, country=country_lower, n_hits=1)
    except Exception as exc:  # pragma: no cover - network/lib dependent
        logger.warning("Google Play 검색 실패(term=%s, country=%s): %s", app_name, country, exc)
        return None

    if not results:
        return None
    top = results[0]
    app_id = top.get("appId")
    title = top.get("title")
    if not app_id:
        return None
    return app_id, title


def lookup_google_play_name_by_id(app_id: str, country: str = "us", lang: str | None = None) -> Optional[str]:
    """
    Lookup Google Play app title by app ID.
    """
    try:
        from google_play_scraper import app as app_detail
    except ImportError:
        logger.error("google-play-scraper 패키지가 필요합니다. --install-missing 옵션을 사용하거나 pip로 설치하세요.")
        return None

    lang_code = lang or country.lower()
    country_lower = country.lower()
    try:
        info = app_detail(app_id, lang=lang_code, country=country_lower)
    except Exception as exc:  # pragma: no cover
        logger.debug("Google Play 앱 이름 조회 실패(app_id=%s, country=%s): %s", app_id, country, exc)
        return None
    return info.get("title")
