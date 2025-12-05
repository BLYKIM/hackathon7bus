import logging
import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from reviews_crawler.apple_app_store_client import fetch_app_store_reviews
from reviews_crawler.google_play_client import fetch_google_play_reviews
from reviews_crawler.app_store_lookup import lookup_app_store_by_id, lookup_app_store_by_name
from reviews_crawler.google_play_lookup import (
    lookup_google_play_by_name,
    lookup_google_play_name_by_id,
)
from reviews_crawler.cli import canonical_store
from reviews_crawler.deps import ensure_dependencies, ensure_api_dependencies
from reviews_crawler.analysis_service import load_reviews_from_jsonl, summarize_reviews
from reviews_crawler.config import load_config
from reviews_crawler.models import normalize_app_name, normalize_user_app_name, to_serializable


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Reviews Crawler API", version="0.2.0")
app.mount("/static", StaticFiles(directory="api/static"), name="static")


class FetchRequest(BaseModel):
    store: str = Field(..., description="google | apple")
    app_id: Optional[str] = Field(None, description="Google Play package or Apple numeric ID")
    app_name: Optional[str] = Field(None, description="App name to search if ID not provided")
    country: str = Field("us", description="Country code, e.g., us, kr")
    max_pages: int = Field(1, ge=1, le=10, description="Number of pages/requests to fetch")
    install_missing: bool = Field(False, description="Auto-install missing dependencies")


class FetchResponse(BaseModel):
    items: List[dict]


class AnalyzeRequest(BaseModel):
    file_path: str = Field(..., description="Path to JSONL file (outputs/...)")
    max_items: Optional[int] = Field(None, description="Override max reviews to read")
    install_missing: bool = Field(False, description="Auto-install API dependencies (fastapi/uvicorn/openai)")


class AnalyzeResponse(BaseModel):
    summary: str


class FetchAnalyzeRequest(BaseModel):
    store: str = Field(..., description="google | apple")
    app_id: Optional[str] = Field(None, description="Google Play package or Apple numeric ID")
    app_name: Optional[str] = Field(None, description="App name to search if ID not provided")
    country: str = Field("kr", description="Country code, default kr")
    max_pages: int = Field(2, ge=1, le=5, description="Pages to fetch (approx 200 reviews for Google)")
    max_items: int = Field(200, ge=1, le=500, description="Max reviews to analyze")
    install_missing: bool = Field(False, description="Auto-install dependencies")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/fetch", response_model=FetchResponse)
def fetch(req: FetchRequest) -> FetchResponse:
    store_canonical = canonical_store(req.store)
    if store_canonical not in {"google-play", "app-store"}:
        raise HTTPException(status_code=400, detail="store must be google or apple")

    ensure_dependencies(store_canonical, auto_install=req.install_missing)
    app_id, app_name = resolve_app_api(
        store_canonical,
        app_id=req.app_id,
        app_name=req.app_name,
        country=req.country,
    )

    records: List[dict] = []
    iterable = (
        fetch_google_play_reviews(app_id=app_id, country=req.country, max_pages=req.max_pages, app_name=app_name)
        if store_canonical == "google-play"
        else fetch_app_store_reviews(app_id=app_id, country=req.country, max_pages=req.max_pages, app_name=app_name)
    )
    for rec in iterable:
        records.append(to_serializable(rec))
    output_path = _build_output_path("fetch", store_canonical, app_id, app_name, req.country)
    _save_jsonl(records, output_path)
    logger.info("Saved fetched reviews to %s (%s records)", output_path, len(records))
    return FetchResponse(items=records)


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    ensure_api_dependencies(req.install_missing)
    config = load_config()
    path = Path(req.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.file_path}")
    max_items = req.max_items or config.max_reviews
    reviews = load_reviews_from_jsonl(path, limit=max_items)
    summary = summarize_reviews(reviews, config=config, target_lang="ko")
    analyzed_path = _build_output_path("analyzed", "analysis", path.stem, None, req.country or "na")
    _save_json_text(summary, analyzed_path)
    logger.info("Analyze summary (full): %s", summary)
    logger.info("Saved analysis to %s", analyzed_path)
    return AnalyzeResponse(summary=summary)


@app.post("/fetch-analyze", response_model=AnalyzeResponse)
def fetch_and_analyze(req: FetchAnalyzeRequest) -> AnalyzeResponse:
    store_canonical = canonical_store(req.store)
    if store_canonical not in {"google-play", "app-store"}:
        raise HTTPException(status_code=400, detail="store must be google or apple")
    ensure_api_dependencies(req.install_missing)
    ensure_dependencies(store_canonical, auto_install=req.install_missing)
    app_id, app_name = resolve_app_api(
        store_canonical,
        app_id=req.app_id,
        app_name=req.app_name,
        country=req.country,
    )
    iterable = (
        fetch_google_play_reviews(app_id=app_id, country=req.country, max_pages=req.max_pages, app_name=app_name)
        if store_canonical == "google-play"
        else fetch_app_store_reviews(app_id=app_id, country=req.country, max_pages=req.max_pages, app_name=app_name)
    )
    reviews = []
    for rec in iterable:
        reviews.append(
            {
                "store": rec.store,
                "app_id": rec.app_id,
                "app_name": rec.app_name,
                "country": rec.country,
                "rating": rec.rating,
                "title": rec.title,
                "body": rec.body,
                "created_at": rec.created_at,
            }
        )
        if len(reviews) >= req.max_items:
            break
    if not reviews:
        raise HTTPException(status_code=404, detail="No reviews fetched")
    config = load_config()
    summary = summarize_reviews(reviews, config=config, target_lang="ko")
    fetch_path = _build_output_path("fetch", store_canonical, app_id, app_name, req.country)
    _save_jsonl(reviews, fetch_path)
    analyzed_path = _build_output_path("analyzed", store_canonical, app_id, app_name, req.country)
    _save_json_text(summary, analyzed_path)
    logger.info("Saved fetched reviews to %s and analysis to %s", fetch_path, analyzed_path)
    logger.info("Fetch-analyze summary (full): %s", summary)
    return AnalyzeResponse(summary=summary)


def resolve_app_api(
    store: str,
    app_id: Optional[str],
    app_name: Optional[str],
    country: str,
) -> tuple[str, Optional[str]]:
    """
    Resolve app_id/app_name for API usage.
    Prefers user-provided name for normalization; otherwise uses lookup result normalized.
    """
    if not app_id and not app_name:
        raise HTTPException(status_code=400, detail="app_id or app_name must be provided")

    user_provided_name = bool(app_name)
    resolved_id = app_id
    resolved_name = app_name

    if store == "app-store":
        if not resolved_id and resolved_name:
            search = lookup_app_store_by_name(resolved_name, country)
            if not search:
                raise HTTPException(status_code=404, detail=f"App not found by name: {resolved_name}")
            resolved_id, found_name = search
            resolved_name = found_name or resolved_name
        elif resolved_id and not resolved_name:
            resolved_name = lookup_app_store_by_id(resolved_id, country) or resolved_name
    elif store == "google-play":
        if not resolved_id and resolved_name:
            search = lookup_google_play_by_name(resolved_name, country)
            if not search:
                raise HTTPException(status_code=404, detail=f"App not found by name: {resolved_name}")
            resolved_id, found_name = search
            resolved_name = found_name or resolved_name
        elif resolved_id and not resolved_name:
            resolved_name = lookup_google_play_name_by_id(resolved_id, country) or resolved_name

    if user_provided_name:
        resolved_name = normalize_user_app_name(resolved_name) or resolved_name
    else:
        resolved_name = normalize_app_name(resolved_name) or resolved_name

    return resolved_id, resolved_name


def _build_output_path(prefix: str, store: str, app_id: str, app_name: Optional[str], country: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    outputs_dir = Path("outputs")
    outputs_dir.mkdir(parents=True, exist_ok=True)
    safe_app_id = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in app_id)
    safe_app_name = ""
    if app_name:
        safe_app_name = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in app_name)
    country_part = country.lower() if country else "na"
    filename = f"{prefix}_{store}_{safe_app_id}"
    if safe_app_name:
        filename += f"_{safe_app_name}"
    filename += f"_{country_part}_{timestamp}.json"
    return outputs_dir / filename


def _save_jsonl(records: List[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _save_json_text(text: str, path: Path) -> None:
    try:
        obj = json.loads(text)
        with path.open("w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except Exception:
        with path.open("w", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
