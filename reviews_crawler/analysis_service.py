import json
import logging
from pathlib import Path
from typing import Iterable, List, Optional

from openai import OpenAI

from .config import AppConfig

logger = logging.getLogger(__name__)


def load_reviews_from_jsonl(file_path: Path, limit: int) -> List[dict]:
    """
    Parse JSONL and extract minimal fields for analysis.
    """
    items: List[dict] = []
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if len(items) >= limit:
                break
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping invalid JSON line in %s", file_path)
                continue
            items.append(
                {
                    "store": obj.get("store"),
                    "app_id": obj.get("app_id"),
                    "app_name": obj.get("app_name"),
                    "country": obj.get("country"),
                    "rating": obj.get("rating"),
                    "title": obj.get("title"),
                    "body": obj.get("body"),
                    "created_at": obj.get("created_at"),
                }
            )
    return items


def summarize_reviews(
    reviews: List[dict],
    config: AppConfig,
    system_prompt: Optional[str] = None,
    target_lang: str = "ko",
) -> str:
    """
    Use OpenAI chat completion to summarize reviews grouped by rating.
    Returns JSON string with {"stats": ..., "llm": ...}.
    """
    if not reviews:
        return "No reviews to analyze."

    sys_prompt = system_prompt or (
        f"You are an app review analyst. Respond ONLY with a JSON object. "
        f"Use language '{target_lang}'. Judge sentiment by content, not by numeric rating. "
        f"Required keys: "
        f"bullets: list of up to 5 concise Korean insights; "
        f"sentiment_counts: object with positive/neutral/negative integers; "
        f"team_insights: object with keys dev, biz, ops (each list of 1-3 Korean, action-oriented bullets focusing on fixes for negative pain points); "
        f"top_positive_reviews: list of up to 5 objects with title, body, rating(optional), created_at(optional), reason; "
        f"top_negative_reviews: same shape, focused on negative content; "
        f"summary_text: short Korean paragraph summarizing the situation. "
        f"Exclude spam/toxic content from positive tops; only include truly positive sentiment."
        f"Do NOT include full review texts, titles, or lists of reviews in the JSON. "
    )

    summary_payload = build_stats(reviews)

    compact_reviews = []
    for r in reviews:
        body = r.get("body") or ""
        compact_reviews.append(
            {
                "title": r.get("title") or "",
                "body": body[:400],  # truncate to reduce tokens
                "rating": r.get("rating"),
                "created_at": r.get("created_at"),
            }
        )

    user_prompt = {
        "task": "Summarize reviews, classify sentiment by content, and extract team-specific insights.",
        "max_items": len(compact_reviews),
        "summary_payload": summary_payload,
        "reviews": compact_reviews,
    }

    client = OpenAI(api_key=config.openai_api_key)
    resp = client.chat.completions.create(
        model=config.model,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
        temperature=0.2,
        max_tokens=2000,
        response_format={"type": "json_object"},
    )

    raw_content = resp.choices[0].message.content
    # logger.info("LLM raw content type=%s, value=%r", type(raw_content), raw_content)

    # 1) content 타입에 따라 llm_data 만들기
    llm_data: dict
    if isinstance(raw_content, dict):
        # 이미 JSON object로 들어온 경우
        llm_data = raw_content
        content_str = json.dumps(raw_content, ensure_ascii=False)
    elif isinstance(raw_content, str):
        content_str = raw_content or "{}"
        try:
            llm_data = json.loads(content_str)
        except Exception as e:
            logger.error("Failed to parse LLM JSON from string: %s", e)
            llm_data = {}
    else:
        # list 등 애매한 타입이면 문자열로 덤프해서 다시 시도
        content_str = json.dumps(raw_content, ensure_ascii=False)
        try:
            llm_data = json.loads(content_str)
        except Exception as e:
            logger.error("Failed to parse LLM JSON from non-str content: %s", e)
            llm_data = {}

    # 2) 각 필드 안전하게 꺼내기
    bullets = llm_data.get("bullets")
    team_insights = llm_data.get("team_insights")
    top_pos = llm_data.get("top_positive_reviews")
    top_neg = llm_data.get("top_negative_reviews")
    summary_text = llm_data.get("summary_text")

    llm_struct = {
        "summary_text": summary_text if isinstance(summary_text, str) else "",
        "bullets": bullets if isinstance(bullets, list) else [],
        "team_insights": team_insights if isinstance(team_insights, dict) else {},
        "top_positive_reviews": top_pos if isinstance(top_pos, list) else [],
        "top_negative_reviews": top_neg if isinstance(top_neg, list) else [],
        "raw": content_str,
    }

    return json.dumps(
        {
            "stats": summary_payload,
            "llm": llm_struct,
        },
        ensure_ascii=False,
        indent=2,
    )


def build_stats(reviews: List[dict]) -> dict:
    total = len(reviews)
    rating_counts = {str(i): 0 for i in range(1, 6)}
    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
    for r in reviews:
        try:
            rating = int(r.get("rating") or 0)
            if 1 <= rating <= 5:
                rating_counts[str(rating)] += 1
        except Exception:
            continue

    classified = []
    for r in reviews:
        label, pos_hits, neg_hits = simple_sentiment_label(r, return_hits=True)
        sentiment_counts[label] = sentiment_counts.get(label, 0) + 1
        classified.append({**r, "sentiment_label": label, "pos_hits": pos_hits, "neg_hits": neg_hits})

    def rating_to_score(r: Optional[int]) -> float:
        if r is None:
            return 0.0
        if r >= 5:
            return 1.0
        if r == 4:
            return 0.6
        if r == 3:
            return 0.0
        if r == 2:
            return -0.6
        return -1.0

    sentiment_scores = [rating_to_score(r.get("rating")) for r in reviews if r.get("rating") is not None]
    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0
    ratings_valid = [r.get("rating") for r in reviews if r.get("rating") is not None]
    avg_rating = sum(ratings_valid) / len(ratings_valid) if ratings_valid else 0.0

    def pick_top(rev_list: List[dict], target: str, limit: int = 5) -> List[dict]:
        filtered = []
        for r in rev_list:
            label = r.get("sentiment_label")
            rating = r.get("rating") or 0
            body = r.get("body") or ""
            pos_hits = r.get("pos_hits", 0)
            neg_hits = r.get("neg_hits", 0)
            if target == "positive":
                if label != "positive":
                    continue
                if rating < 4:
                    continue
                if neg_hits > 0:
                    continue
                if pos_hits <= 0:
                    continue
                if len(body) < 20:
                    continue
            if target == "negative":
                if label != "negative":
                    continue
            filtered.append(r)
        filtered.sort(key=lambda x: len(x.get("body") or ""), reverse=True)
        return filtered[:limit]

    top_pos = pick_top(classified, target="positive", limit=5)
    top_neg = pick_top(classified, target="negative", limit=5)

    return {
        "total_reviews": total,
        "rating_counts": rating_counts,
        "avg_rating": avg_rating,
        "avg_sentiment_score": avg_sentiment,
        "sentiment_counts": sentiment_counts,
        "top_positive_reviews": top_pos,
        "top_negative_reviews": top_neg,
    }


def simple_sentiment_label(review: dict, return_hits: bool = False):
    """
    Very lightweight heuristic sentiment by content, falling back to rating.
    Negative keywords override rating if present.
    """
    text = f"{review.get('title','')} {review.get('body','')}".lower()
    neg_keywords = [
        "bad", "worst", "terrible", "hate", "angry", "trash", "garbage", "scam",
        "bug", "error", "crash", "ban", "banned", "problem", "issue", "not work",
        "disappoint", "refund", "annoy", "lag", "slow", "ads", "ad", "too many ads", "advert",
        "불편", "별로", "최악", "혐오", "개악", "짜증", "오류", "버그", "렉", "강제", "폭주",
        "안됨", "안 돼", "싫", "에러", "비싸", "과금", "환불", "나쁨", "악화",
        "짜증나", "빡치", "개같", "ㅅㅂ", "ㅂㅅ", "쓰레기", "사기", "구려", "구린", "실망",
        "불만", "혐", "욕", "problematic", "annoying", "frustrat", "disgust", "hate",
        "광고", "ad ", "ads", "광고비", "쇼츠 광고", "프리미엄 광고",
    ]
    pos_keywords = [
        "great", "love", "awesome", "good", "nice", "best", "amazing", "happy", "like",
        "감사", "좋", "추천", "최고", "만족", "사랑", "훌륭", "편리",
    ]

    neg_hits = sum(k in text for k in neg_keywords)
    pos_hits = sum(k in text for k in pos_keywords)

    try:
        rating = int(review.get("rating"))
    except Exception:
        rating = None

    # Strong negative override
    if neg_hits > 0:
        return ("negative", pos_hits, neg_hits) if return_hits else "negative"

    if pos_hits > 0 and neg_hits == 0:
        return ("positive", pos_hits, neg_hits) if return_hits else "positive"

    if rating is None:
        return ("neutral", pos_hits, neg_hits) if return_hits else "neutral"
    if rating >= 4 and neg_hits == 0:
        return ("positive", pos_hits, neg_hits) if return_hits else "positive"
    if rating <= 2:
        return ("negative", pos_hits, neg_hits) if return_hits else "negative"
    return ("neutral", pos_hits, neg_hits) if return_hits else "neutral"
