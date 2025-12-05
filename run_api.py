"""
API 서버 실행 스크립트. FastAPI/uvicorn이 없을 경우 --install-missing 로 자동 설치 후 실행.
"""

import argparse
import logging
import sys

from reviews_crawler.deps import ensure_api_dependencies


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run Reviews Crawler API server (FastAPI).")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument(
        "--install-missing",
        action="store_true",
        help="Auto-install FastAPI/uvicorn if missing.",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (development use).",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ensure_api_dependencies(auto_install=args.install_missing)
    try:
        import uvicorn
    except ImportError:
        logging.error("uvicorn import failed even after install.")
        sys.exit(1)

    uvicorn.run("api.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
