import importlib.util
import logging
import subprocess
import sys
from typing import Iterable, List


logger = logging.getLogger(__name__)


GOOGLE_PLAY_PACKAGE = "google-play-scraper"
REQUESTS_PACKAGE = "requests"
FASTAPI_PACKAGE = "fastapi"
UVICORN_PACKAGE = "uvicorn"
OPENAI_PACKAGE = "openai"


def _is_installed(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _pip_install(packages: Iterable[str]) -> bool:
    """
    Attempt to install the given packages with pip.
    Returns True if installation succeeds, False otherwise.
    """
    cmd = [sys.executable, "-m", "pip", "install", *packages]
    logger.info("Installing missing packages via pip: %s", " ".join(packages))
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to invoke pip: %s", exc)
        return False

    if result.returncode != 0:
        logger.error("pip install failed (%s): %s", result.returncode, result.stderr.strip())
        return False

    logger.info("pip install succeeded: %s", result.stdout.strip() or "ok")
    return True


def ensure_dependencies(store: str, auto_install: bool) -> None:
    """
    Ensure required dependencies exist. Optionally auto-installs missing packages.
    Raises SystemExit if required deps are missing and auto_install is False or install fails.
    """
    missing: List[str] = []
    if not _is_installed("requests"):
        missing.append(REQUESTS_PACKAGE)
    if store == "google-play" and not _is_installed("google_play_scraper"):
        missing.append(GOOGLE_PLAY_PACKAGE)

    if not missing:
        return

    if not auto_install:
        logger.error(
            "Missing required packages: %s. Re-run with --install-missing to auto-install.",
            ", ".join(missing),
        )
        raise SystemExit(1)

    if not _pip_install(missing):
        raise SystemExit(1)


def ensure_api_dependencies(auto_install: bool) -> None:
    """
    Ensure FastAPI/uvicorn exist for running the API server.
    """
    missing = []
    if not _is_installed("fastapi"):
        missing.append(FASTAPI_PACKAGE)
    if not _is_installed("uvicorn"):
        missing.append(UVICORN_PACKAGE)
    if not _is_installed("openai"):
        missing.append(OPENAI_PACKAGE)
    if not missing:
        return
    if not auto_install:
        logger.error(
            "Missing required packages for API server: %s. Re-run with --install-missing to auto-install.",
            ", ".join(missing),
        )
        raise SystemExit(1)
    if not _pip_install(missing):
        raise SystemExit(1)
