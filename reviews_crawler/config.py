import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    openai_api_key: str
    max_reviews: int = 50
    model: str = "gpt-4o-mini"


DEFAULT_CONFIG_PATH = "config.json"


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """
    Load configuration from environment variables or JSON file.
    Priority: explicit path -> env file path -> env vars.
    """
    env_key = os.getenv("OPENAI_API_KEY")
    env_max_reviews = os.getenv("REVIEW_ANALYZER_MAX_REVIEWS")
    env_model = os.getenv("REVIEW_ANALYZER_MODEL")

    if config_path is None:
        config_path = os.getenv("REVIEW_ANALYZER_CONFIG", DEFAULT_CONFIG_PATH)

    file_conf = {}
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                file_conf = json.load(f)
        except Exception as exc:
            logger.warning("Failed to load config file %s: %s", config_path, exc)

    api_key = env_key or file_conf.get("openai_api_key")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY가 설정되지 않았습니다. 환경변수나 config 파일을 확인하세요.")

    max_reviews = int(env_max_reviews or file_conf.get("max_reviews") or 50)
    model = env_model or file_conf.get("model") or "gpt-4o-mini"

    return AppConfig(openai_api_key=api_key, max_reviews=max_reviews, model=model)
