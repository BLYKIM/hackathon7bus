import argparse
import json
import logging
import pathlib
import sys
from datetime import datetime, timezone
from typing import Iterable

from .apple_app_store_client import fetch_app_store_reviews
from .google_play_client import fetch_google_play_reviews
from .models import ReviewRecord, to_serializable, normalize_app_name, normalize_user_app_name
from .deps import ensure_dependencies
from .app_store_lookup import lookup_app_store_by_name, lookup_app_store_by_id
from .google_play_lookup import lookup_google_play_by_name, lookup_google_play_name_by_id


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch public app reviews from app stores.")
    parser.add_argument(
        "--store",
        required=True,
        choices=["google", "apple"],
        help="Target store to crawl. google | apple",
    )
    parser.add_argument(
        "--app-id",
        required=False,
        help="Google Play 패키지명 또는 Apple 숫자 앱 ID. --app-name으로 대체 가능.",
    )
    parser.add_argument(
        "--app-name",
        required=False,
        help="앱 이름(특히 App Store). 제공 시 iTunes Search API로 ID를 찾습니다.",
    )
    parser.add_argument(
        "--country",
        default="us",
        help="Store country code (default: us).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="Maximum number of pages/requests to fetch (default: 1).",
    )
    parser.add_argument(
        "--install-missing",
        action="store_true",
        help="Automatically install missing dependencies via pip.",
    )
    return parser.parse_args(argv)


def iter_reviews(store: str, args: argparse.Namespace, app_id: str, app_name: str | None) -> Iterable[ReviewRecord]:
    if store == "google-play":
        return fetch_google_play_reviews(
            app_id=app_id,
            country=args.country,
            max_pages=args.max_pages,
            app_name=app_name,
        )

    return fetch_app_store_reviews(
        app_id=app_id,
        country=args.country,
        max_pages=args.max_pages,
        app_name=app_name,
    )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure_logging()
    logger = logging.getLogger(__name__)
    store_canonical = canonical_store(args.store)
    ensure_dependencies(store_canonical, auto_install=args.install_missing)
    app_id, app_name_raw, user_provided_name = resolve_app(args, store_canonical)
    if user_provided_name:
        app_name = normalize_user_app_name(app_name_raw) or app_name_raw
    else:
        app_name = normalize_app_name(app_name_raw) or app_name_raw
    output_path = _build_output_path(store_canonical, app_id, args.country, app_name)
    logger.info(
        "Starting review fetch store=%s app_id=%s country=%s max_pages=%s output=%s",
        store_canonical,
        app_id,
        args.country,
        args.max_pages,
        output_path,
    )

    records = iter_reviews(store_canonical, args, app_id=app_id, app_name=app_name)
    writer = output_path.open("a", encoding="utf-8")

    try:
        for record in records:
            writer.write(json.dumps(to_serializable(record), ensure_ascii=False) + "\n")
            writer.flush()
    finally:
        writer.close()

    logger.info("Finished review fetch")


def _build_output_path(store: str, app_id: str, country: str, app_name: str | None) -> pathlib.Path:
    """
    Build an output path under outputs/ using store, app_id, app_name, country, and UTC timestamp (minute-level).
    """
    outputs_dir = pathlib.Path("outputs")
    outputs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    safe_app_id = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in app_id)
    country_lower = country.lower()
    safe_app_name = None
    if app_name:
        safe_app_name = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in app_name)
    name_part = safe_app_name or safe_app_id
    filename = f"{store}_{safe_app_id}_{name_part}_{country_lower}_{timestamp}.jsonl"
    return outputs_dir / filename


def resolve_app(args: argparse.Namespace, store_canonical: str) -> tuple[str, str | None, bool]:
    """
    Resolve app_id and app_name based on CLI arguments.
    For App Store, app-name만 주어지면 iTunes Search API로 ID를 찾습니다.
    For Google Play, app-name만 주어지면 search API로 app_id를 찾습니다.
    """
    if not args.app_id and not args.app_name:
        raise SystemExit("반드시 --app-id 또는 --app-name 중 하나는 제공해야 합니다.")

    app_id = args.app_id
    app_name = args.app_name
    user_provided_name = bool(args.app_name)

    if store_canonical == "app-store":
        if not app_id and app_name:
            result = lookup_app_store_by_name(app_name, args.country)
            if not result:
                raise SystemExit(f"앱 이름으로 App Store ID를 찾지 못했습니다: {app_name}")
            app_id, found_name = result
            app_name = found_name or app_name
        elif app_id and not app_name:
            found_name = lookup_app_store_by_id(app_id, args.country)
            app_name = found_name or app_name
    elif store_canonical == "google-play":
        if not app_id and app_name:
            result = lookup_google_play_by_name(app_name, args.country)
            if not result:
                raise SystemExit(f"앱 이름으로 Google Play ID를 찾지 못했습니다: {app_name}")
            app_id, found_name = result
            app_name = found_name or app_name
        elif app_id and not app_name:
            app_name = lookup_google_play_name_by_id(app_id, args.country) or app_name
    return app_id, app_name, user_provided_name


def canonical_store(store_arg: str) -> str:
    if store_arg == "google":
        return "google-play"
    if store_arg == "apple":
        return "app-store"
    return store_arg


if __name__ == "__main__":
    main()
