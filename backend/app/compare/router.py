import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.auth.service import get_current_user
from app.database import get_connection
from app.trends.router import _normalize, _ensure_keyword_tracked, _has_fresh_data
from app.scheduler.jobs import scrape_single_keyword

router = APIRouter(prefix="/api/compare", tags=["compare"])

MAX_COMPARE = 6  # Max keywords per comparison


@router.get("")
def get_comparison(user: str = Depends(get_current_user)):
    """Get the current user's saved comparison list with latest scores."""
    conn = get_connection()

    rows = conn.execute(
        "SELECT keyword, added_at FROM user_comparisons WHERE user_email = ? ORDER BY added_at ASC",
        (user,),
    ).fetchall()

    keywords = [r["keyword"] for r in rows]

    # Fetch latest scores for each keyword
    result = []
    for kw in keywords:
        score_row = conn.execute(
            "SELECT composite_score, volume_growth, price_growth, lifecycle_stage FROM trend_scores "
            "WHERE keyword = ? AND period_days = 7 ORDER BY computed_at DESC LIMIT 1",
            (kw,),
        ).fetchone()
        result.append({
            "keyword": kw,
            "composite_score": score_row["composite_score"] if score_row else None,
            "volume_growth": score_row["volume_growth"] if score_row else None,
            "price_growth": score_row["price_growth"] if score_row else None,
            "lifecycle_stage": score_row["lifecycle_stage"] if score_row else None,
        })

    conn.close()
    return {"keywords": result}


@router.post("/{keyword}")
def add_to_comparison(keyword: str, user: str = Depends(get_current_user)):
    """Add a keyword to the user's comparison list. Triggers an on-demand scrape if no fresh data."""
    keyword = _normalize(keyword)
    conn = get_connection()

    # Check limit
    count = conn.execute(
        "SELECT COUNT(*) as cnt FROM user_comparisons WHERE user_email = ?", (user,)
    ).fetchone()["cnt"]

    if count >= MAX_COMPARE:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_COMPARE} keywords can be compared at once. Remove one first."
        )

    conn.execute(
        "INSERT OR IGNORE INTO user_comparisons (user_email, keyword) VALUES (?, ?)",
        (user, keyword),
    )
    conn.commit()
    conn.close()

    # Ensure keyword is tracked, then scrape if no fresh data
    _ensure_keyword_tracked(keyword)
    if not _has_fresh_data(keyword):
        thread = threading.Thread(target=scrape_single_keyword, args=(keyword,))
        thread.start()
        thread.join(timeout=30)

    return {"message": f"'{keyword}' added to comparison"}


@router.delete("/{keyword}")
def remove_from_comparison(keyword: str, user: str = Depends(get_current_user)):
    """Remove a keyword from the user's comparison list."""
    keyword = keyword.lower().strip()
    conn = get_connection()
    conn.execute(
        "DELETE FROM user_comparisons WHERE user_email = ? AND keyword = ?",
        (user, keyword),
    )
    conn.commit()
    conn.close()
    return {"message": f"'{keyword}' removed from comparison"}


@router.delete("")
def clear_comparison(user: str = Depends(get_current_user)):
    """Clear the entire comparison list."""
    conn = get_connection()
    conn.execute("DELETE FROM user_comparisons WHERE user_email = ?", (user,))
    conn.commit()
    conn.close()
    return {"message": "Comparison cleared"}


@router.get("/public-data")
def get_public_comparison_data(keywords: str = "", period: int = 30):
    """Get comparison data for a comma-separated list of keywords. No auth required."""
    kw_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]
    return _build_series(kw_list, period)


def _build_series(keywords: list, period: int) -> dict:
    from datetime import datetime, timedelta, timezone
    conn = get_connection()
    start = (datetime.now(timezone.utc) - timedelta(days=period)).isoformat()
    series = []
    for kw in keywords:
        volume_rows = conn.execute(
            "SELECT AVG(value) as value, DATE(recorded_at) as recorded_at FROM trend_data "
            "WHERE keyword = ? AND source = 'google_trends' AND metric = 'search_volume' "
            "AND recorded_at >= ? GROUP BY DATE(recorded_at) ORDER BY recorded_at ASC",
            (kw, start),
        ).fetchall()
        score_row = conn.execute(
            "SELECT composite_score, volume_growth, price_growth, lifecycle_stage "
            "FROM trend_scores WHERE keyword = ? AND period_days = ? "
            "ORDER BY computed_at DESC LIMIT 1",
            (kw, period),
        ).fetchone()
        if not score_row:
            score_row = conn.execute(
                "SELECT composite_score, volume_growth, price_growth, lifecycle_stage "
                "FROM trend_scores WHERE keyword = ? "
                "ORDER BY ABS(period_days - ?) ASC, computed_at DESC LIMIT 1",
                (kw, period),
            ).fetchone()
        price_row = conn.execute(
            "SELECT value FROM trend_data "
            "WHERE keyword = ? AND source IN ('ebay','poshmark','depop','etsy') AND metric = 'avg_price' "
            "ORDER BY recorded_at DESC LIMIT 1",
            (kw,),
        ).fetchone()
        series.append({
            "keyword": kw,
            "volume": [{"date": r["recorded_at"], "value": r["value"]} for r in volume_rows],
            "composite_score": score_row["composite_score"] if score_row else None,
            "volume_growth": score_row["volume_growth"] if score_row else None,
            "price_growth": score_row["price_growth"] if score_row else None,
            "lifecycle_stage": score_row["lifecycle_stage"] if score_row else None,
            "avg_price": price_row["value"] if price_row else None,
        })
    conn.close()
    return {"keywords": keywords, "series": series}


@router.get("/data")
def get_comparison_data(period: int = 30, user: str = Depends(get_current_user)):
    """Get time series data for all keywords in the user's comparison list."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT keyword FROM user_comparisons WHERE user_email = ? ORDER BY added_at ASC",
        (user,),
    ).fetchall()
    keywords = [r["keyword"] for r in rows]
    conn.close()
    if not keywords:
        return {"keywords": [], "series": []}
    return _build_series(keywords, period)
