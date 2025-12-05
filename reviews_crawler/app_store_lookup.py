import logging
from typing import Optional, Tuple


logger = logging.getLogger(__name__)


def lookup_app_store_by_name(app_name: str, country: str = "us") -> Optional[Tuple[str, str]]:
    """
    Search the iTunes Search API by name and return (app_id, app_name) if found.
    """
    try:
        import requests  # type: ignore
    except ImportError:
        logger.error("requests 패키지가 필요합니다. --install-missing 옵션을 사용하거나 pip로 설치하세요.")
        return None

    url = "https://itunes.apple.com/search"
    params = {
        "term": app_name,
        "country": country.lower(),
        "entity": "software",
        "limit": 1,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("App Store 검색 실패(term=%s, country=%s): %s", app_name, country, exc)
        return None

    results = data.get("results") or []
    if not results:
        return None
    top = results[0]
    track_id = top.get("trackId")
    track_name = top.get("trackName")
    if not track_id:
        return None
    return str(track_id), track_name


def lookup_app_store_by_id(app_id: str, country: str = "us") -> Optional[str]:
    """
    Lookup the official app name via iTunes lookup API by app ID.
    """
    try:
        import requests  # type: ignore
    except ImportError:
        logger.error("requests 패키지가 필요합니다. --install-missing 옵션을 사용하거나 pip로 설치하세요.")
        return None

    url = "https://itunes.apple.com/lookup"
    params = {"id": app_id, "country": country.lower()}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # pragma: no cover
        logger.debug("App Store ID lookup 실패(app_id=%s, country=%s): %s", app_id, country, exc)
        return None

    results = data.get("results") or []
    if not results:
        return None
    return results[0].get("trackName")
