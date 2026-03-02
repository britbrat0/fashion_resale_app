import logging
import threading
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse

from app.auth.service import get_current_user
from app.database import get_connection
from app.trends.service import get_top_trends, get_keyword_details, compute_composite_score, predict_stage_warning
from app.scheduler.jobs import scrape_single_keyword
from app.scrapers.discovery import classify_keyword_scale

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trends", tags=["trends"])

# How old data can be before triggering on-demand scrape (in hours)
STALE_THRESHOLD_HOURS = 6

# Auto-expire user_search keywords inactive for this many days
USER_KEYWORD_EXPIRY_DAYS = 30


def _normalize(keyword: str) -> str:
    """Normalize keyword: lowercase, strip, collapse whitespace."""
    return re.sub(r'\s+', ' ', keyword.lower().strip())


def _is_duplicate(keyword: str, conn) -> bool:
    """Check if a normalized keyword already exists under a different form."""
    row = conn.execute(
        "SELECT keyword FROM keywords WHERE keyword = ? AND status != 'inactive'",
        (keyword,),
    ).fetchone()
    return row is not None


def _has_fresh_data(keyword: str) -> bool:
    """Check if we have recent data (< STALE_THRESHOLD_HOURS old) from all configured sources."""
    conn = get_connection()
    threshold = (datetime.now(timezone.utc) - timedelta(hours=STALE_THRESHOLD_HOURS)).isoformat()

    sources = conn.execute(
        "SELECT DISTINCT source FROM trend_data WHERE keyword = ? AND recorded_at >= ?",
        (keyword, threshold),
    ).fetchall()
    conn.close()

    fresh_sources = {r["source"] for r in sources}

    if "google_trends" not in fresh_sources:
        return False

    from app.config import settings
    if settings.ebay_app_id and settings.ebay_cert_id and "ebay" not in fresh_sources:
        return False
    if settings.etsy_api_key and "etsy" not in fresh_sources:
        return False

    return True


def _merge_keyword_data(source: str, target: str, conn):
    """Re-label all data rows from source keyword to target, then deactivate source."""
    # trend_data and trend_scores have no unique constraints — safe to re-label directly
    conn.execute("UPDATE trend_data SET keyword = ? WHERE keyword = ?", (target, source))
    conn.execute("UPDATE trend_scores SET keyword = ? WHERE keyword = ?", (target, source))

    # trend_images has UNIQUE(keyword, image_url) — drop conflicting source rows first
    conn.execute(
        """DELETE FROM trend_images WHERE keyword = ? AND image_url IN (
               SELECT image_url FROM trend_images WHERE keyword = ?
           )""",
        (source, target),
    )
    conn.execute("UPDATE trend_images SET keyword = ? WHERE keyword = ?", (target, source))

    # Deactivate the duplicate keyword
    conn.execute("UPDATE keywords SET status = 'inactive' WHERE keyword = ?", (source,))
    logger.info(f"Merged keyword '{source}' into '{target}'")


def _ensure_keyword_tracked(keyword: str):
    """Add keyword to keywords table if not already present. Updates last_searched_at on each search.
    Always tracks the keyword exactly as searched — no similarity redirects for user searches."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()

    existing = conn.execute(
        "SELECT keyword, status, scale FROM keywords WHERE keyword = ?", (keyword,)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE keywords SET last_searched_at = ?, status = CASE WHEN status = 'inactive' THEN 'active' ELSE status END WHERE keyword = ?",
            (now, keyword),
        )
        needs_classification = existing["scale"] is None
    else:
        conn.execute(
            "INSERT INTO keywords (keyword, source, status, last_searched_at) VALUES (?, 'user_search', 'active', ?)",
            (keyword, now),
        )
        needs_classification = True

    conn.commit()
    conn.close()

    if needs_classification:
        def _classify():
            scale = classify_keyword_scale(keyword)
            c = get_connection()
            c.execute("UPDATE keywords SET scale = ? WHERE keyword = ?", (scale, keyword))
            c.commit()
            c.close()
            logger.info(f"Scale: '{keyword}' → {scale}")
        threading.Thread(target=_classify, daemon=True).start()

    return keyword


@router.get("/top")
def top_trends(period: int = 7, user: str = Depends(get_current_user)):
    """Get top 10 emerging trends for a given time period."""
    trends = get_top_trends(period_days=period, limit=10)
    return {
        "period_days": period,
        "trends": trends,
    }


@router.get("/similar")
def check_similar(keyword: str, user: str = Depends(get_current_user)):
    """Check if a keyword is similar to an already-tracked keyword using word-overlap matching.
    Returns { similar: <keyword> } or { similar: null }. Does not modify the DB.
    No Claude call — uses deterministic word-set containment:
      'corporate goth' words {'corporate','goth'} ⊇ tracked 'goth' words {'goth'} → suggest
      'punk' words {'punk'} shares nothing with 'goth' words {'goth'} → no suggestion
      'goth' words {'goth'} shares nothing with 'dark academia' words {'dark','academia'} → no suggestion
    """
    kw = _normalize(keyword)
    conn = get_connection()

    # If already actively tracked, no suggestion needed
    existing = conn.execute(
        "SELECT keyword FROM keywords WHERE keyword = ? AND status != 'inactive'", (kw,)
    ).fetchone()
    if existing:
        conn.close()
        return {"similar": None}

    rows = conn.execute(
        "SELECT keyword FROM keywords WHERE status != 'inactive'"
    ).fetchall()
    tracked = [r[0] for r in rows if r[0] != kw]
    conn.close()

    kw_words = set(kw.split())

    # A tracked keyword is a candidate only when all its words appear in the search term
    # OR all search term words appear in the tracked keyword.
    # This catches "corporate goth" → "goth" and "y2k fashion" → "y2k"
    # but NOT "punk" → "goth" or "goth" → "dark academia".
    candidates = [
        k for k in tracked
        if set(k.split()).issubset(kw_words) or kw_words.issubset(set(k.split()))
    ]

    if not candidates:
        return {"similar": None}

    # Among candidates pick the most specific (most words = most specific match)
    best = max(candidates, key=lambda k: len(k.split()))
    return {"similar": best}


@router.get("/search")
def search_trend(keyword: str, period: int = 7, background_tasks: BackgroundTasks = None, user: str = Depends(get_current_user)):
    """Search a custom keyword. Triggers on-demand scrape if no fresh data."""
    keyword = _normalize(keyword)
    keyword = _ensure_keyword_tracked(keyword)

    if not _has_fresh_data(keyword):
        thread = threading.Thread(target=scrape_single_keyword, args=(keyword,))
        thread.start()
        thread.join(timeout=30)

    details = get_keyword_details(keyword, period_days=period)
    score = compute_composite_score(keyword, period)

    return {
        "keyword": keyword,
        "period_days": period,
        "score": score,
        "details": details,
    }


@router.get("/ranking-forecast")
def ranking_forecast(period: int = 7, user: str = Depends(get_current_user)):
    """Project 7-day rank changes for all tracked trends.

    Returns:
      - top10: current top-10 trends with projected_rank, rank_delta, stage_warning
      - challengers: up to 3 rising trends (ranked 11+) with positive volume slope
      - horizon_days: forecast horizon used
    """
    from app.forecasting.model import get_volume_slope

    HORIZON = 7

    conn = get_connection()
    rows = conn.execute(
        "SELECT ts.keyword, ts.composite_score, ts.volume_growth, ts.price_growth, "
        "ts.lifecycle_stage, COALESCE(k.scale, 'macro') as scale "
        "FROM trend_scores ts LEFT JOIN keywords k ON ts.keyword = k.keyword "
        "WHERE ts.period_days = ? AND (k.status IS NULL OR k.status != 'inactive')",
        (period,),
    ).fetchall()
    conn.close()

    all_kws = [dict(r) for r in rows]
    if not all_kws:
        return {"top10": [], "challengers": [], "horizon_days": HORIZON, "period_days": period}

    # Compute volume slope and project scores forward HORIZON days
    for kw in all_kws:
        slope, current_vol = get_volume_slope(kw["keyword"])
        kw["slope"] = slope
        # Estimate how much volume_growth will shift over the horizon
        if current_vol > 0:
            delta_pct = (slope * HORIZON / current_vol) * 100.0
        else:
            delta_pct = 0.0
        proj_vg = (kw["volume_growth"] or 0.0) + delta_pct
        proj_composite = 0.6 * proj_vg + 0.4 * (kw["price_growth"] or 0.0)
        kw["projected_volume_growth"] = round(proj_vg, 1)
        kw["projected_composite"] = round(proj_composite, 1)
        kw["stage_warning"] = predict_stage_warning(
            kw["lifecycle_stage"] or "Peak",
            kw["volume_growth"] or 0.0,
            proj_vg,
            slope,
        )

    # Helper: assign percentile within a scale group (mirrors get_top_trends logic)
    def _rank_group(group, score_key):
        group = sorted(group, key=lambda t: t[score_key] or 0, reverse=True)
        n = len(group)
        for i, t in enumerate(group):
            t[f"_pct_{score_key}"] = (n - i) / n if n > 0 else 0.5
        return group

    # Current ranks
    macro = [k for k in all_kws if k["scale"] == "macro"]
    micro = [k for k in all_kws if k["scale"] == "micro"]
    _rank_group(macro, "composite_score")
    _rank_group(micro, "composite_score")
    current_combined = sorted(
        macro + micro, key=lambda t: t["_pct_composite_score"], reverse=True
    )
    for i, kw in enumerate(current_combined):
        kw["current_rank"] = i + 1

    # Projected ranks
    _rank_group(macro, "projected_composite")
    _rank_group(micro, "projected_composite")
    projected_combined = sorted(
        macro + micro, key=lambda t: t["_pct_projected_composite"], reverse=True
    )
    for i, kw in enumerate(projected_combined):
        kw["projected_rank"] = i + 1

    for kw in all_kws:
        kw["rank_delta"] = kw["current_rank"] - kw["projected_rank"]  # positive = rising

    # Top 10 by current rank
    top10 = sorted(all_kws, key=lambda k: k["current_rank"])[:10]

    # Challengers: currently ranked 11+ with positive slope
    challengers = [k for k in all_kws if k["current_rank"] > 10 and k["slope"] > 0]
    challengers.sort(key=lambda k: k["slope"], reverse=True)
    challengers = challengers[:3]

    def _fmt(kw):
        return {
            "keyword": kw["keyword"],
            "current_rank": kw["current_rank"],
            "projected_rank": kw["projected_rank"],
            "rank_delta": kw["rank_delta"],
            "composite_score": kw["composite_score"],
            "projected_composite": kw["projected_composite"],
            "lifecycle_stage": kw["lifecycle_stage"],
            "stage_warning": kw["stage_warning"],
            "slope": round(kw["slope"], 3),
            "scale": kw["scale"],
        }

    return {
        "top10": [_fmt(k) for k in top10],
        "challengers": [_fmt(k) for k in challengers],
        "horizon_days": HORIZON,
        "period_days": period,
    }


# Refresh Pinterest images in the background after this many hours
PINTEREST_IMAGE_STALE_HOURS = 6


def _pinterest_images_stale(keyword: str) -> bool:
    """Return True if Pinterest images for this keyword are older than PINTEREST_IMAGE_STALE_HOURS."""
    threshold = (datetime.now(timezone.utc) - timedelta(hours=PINTEREST_IMAGE_STALE_HOURS)).isoformat()
    conn = get_connection()
    row = conn.execute(
        "SELECT scraped_at FROM trend_images WHERE keyword = ? AND source = 'pinterest' "
        "ORDER BY scraped_at DESC LIMIT 1",
        (keyword,),
    ).fetchone()
    conn.close()
    if not row:
        return True
    return row["scraped_at"] < threshold


@router.get("/{keyword}/images")
def trend_images(keyword: str, user: str = Depends(get_current_user)):
    """Return up to 4 product images. Primary: Pinterest. Fallback: eBay.
    Returns cached images immediately; triggers a background refresh if cache is stale."""
    keyword = _normalize(keyword)

    def _dedup_phash(images, threshold=10):
        try:
            import imagehash
        except ImportError:
            return images
        seen_hashes = []
        result = []
        for img in images:
            ph_str = img.get("phash")
            if ph_str:
                try:
                    ph = imagehash.hex_to_hash(ph_str)
                    if any(abs(ph - s) <= threshold for s in seen_hashes):
                        continue
                    seen_hashes.append(ph)
                except Exception:
                    pass
            result.append(img)
        return result

    def _query_db():
        from app.scrapers.pinterest import _is_article_pin
        conn = get_connection()
        rows = conn.execute(
            "SELECT image_url, source, title, price, item_url, phash FROM trend_images "
            "WHERE keyword = ? ORDER BY scraped_at DESC LIMIT 20",
            (keyword,),
        ).fetchall()
        conn.close()
        seen_urls = set()
        pinterest_imgs, ebay_imgs = [], []
        for r in rows:
            d = dict(r)
            url = d.get("image_url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            if d["source"] == "pinterest":
                if not _is_article_pin(d.get("title") or ""):
                    pinterest_imgs.append(d)
            else:
                ebay_imgs.append(d)
        # Deduplicate visually similar images using perceptual hash
        pinterest_imgs = _dedup_phash(pinterest_imgs)
        ebay_imgs = _dedup_phash(ebay_imgs)
        # Pinterest first, fill remaining slots with eBay
        combined = pinterest_imgs[:4]
        combined += ebay_imgs[:4 - len(combined)]
        return combined

    images = _query_db()
    pinterest_count = sum(1 for img in images if img["source"] == "pinterest")

    if pinterest_count < 4:
        # No cached images yet — block and wait so the first load has content
        from app.scrapers.pinterest import scrape_pinterest_images
        t = threading.Thread(target=scrape_pinterest_images, args=(keyword,))
        t.start()
        t.join(timeout=20)
        images = _query_db()
    elif _pinterest_images_stale(keyword):
        # Cached images exist but are old — refresh in background, return stale images now
        from app.scrapers.pinterest import scrape_pinterest_images
        threading.Thread(target=scrape_pinterest_images, args=(keyword,), daemon=True).start()

    response = JSONResponse({"keyword": keyword, "images": images})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


@router.get("/{keyword}/details")
def trend_details(keyword: str, period: int = 7, user: str = Depends(get_current_user)):
    """Get full trend detail for a specific keyword."""
    details = get_keyword_details(_normalize(keyword), period_days=period)
    return details


@router.get("/{keyword}/seasonal")
def trend_seasonal(keyword: str, user: str = Depends(get_current_user)):
    """Get seasonal search_volume pattern by month-of-year for a keyword."""
    from app.trends.seasonal import get_seasonal_pattern
    return {"keyword": _normalize(keyword), "seasonal": get_seasonal_pattern(_normalize(keyword))}


@router.get("/{keyword}/correlations")
def trend_correlations(keyword: str, period: int = 30, top: int = 5, user: str = Depends(get_current_user)):
    """Get keywords most correlated with this keyword's search_volume trend."""
    from app.trends.correlation import get_keyword_correlations
    return {
        "keyword": _normalize(keyword),
        "period_days": period,
        "correlations": get_keyword_correlations(_normalize(keyword), period_days=period, top_n=top),
    }


@router.get("/{keyword}/forecast")
def trend_forecast(keyword: str, horizon: int = 14, user: str = Depends(get_current_user)):
    """Forecast future search volume for a keyword using polynomial regression."""
    from app.forecasting.model import forecast_search_volume
    return forecast_search_volume(_normalize(keyword), horizon_days=horizon)


@router.get("/{keyword}/regions")
def trend_regions(keyword: str, scope: str = "us", user: str = Depends(get_current_user)):
    """Get region heatmap data for a keyword. scope: 'us' or 'global'."""
    keyword = _normalize(keyword)
    conn = get_connection()

    metric = "search_volume_region_global" if scope == "global" else "search_volume_region"

    rows = conn.execute(
        "SELECT region, value FROM trend_data WHERE keyword = ? AND metric = ? ORDER BY value DESC",
        (keyword, metric),
    ).fetchall()
    conn.close()

    return {
        "keyword": keyword,
        "scope": scope,
        "regions": [{"region": r["region"], "value": r["value"]} for r in rows],
    }


@router.get("/keywords/list")
def list_keywords(user: str = Depends(get_current_user)):
    """List all tracked keywords and their status."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT keyword, source, status, scale, added_at, last_searched_at FROM keywords WHERE status != 'inactive' ORDER BY added_at DESC"
    ).fetchall()
    conn.close()
    return {"keywords": [dict(r) for r in rows]}


@router.post("/keywords/{keyword}/track")
def track_keyword(keyword: str, user: str = Depends(get_current_user)):
    """Add a keyword to tracking and kick off an immediate background scrape."""
    keyword = _normalize(keyword)
    _ensure_keyword_tracked(keyword)
    threading.Thread(target=scrape_single_keyword, args=(keyword,), daemon=True).start()
    return {"keyword": keyword, "status": "tracking"}


@router.post("/keywords/{keyword}/activate")
def activate_keyword(keyword: str, user: str = Depends(get_current_user)):
    """Promote a pending_review keyword to active."""
    conn = get_connection()
    conn.execute("UPDATE keywords SET status = 'active' WHERE keyword = ?", (_normalize(keyword),))
    conn.commit()
    conn.close()
    return {"message": f"Keyword '{keyword}' activated"}


@router.delete("/keywords/{keyword}")
def remove_keyword(keyword: str, user: str = Depends(get_current_user)):
    """Deactivate a user-searched keyword. Seed keywords are protected."""
    keyword = _normalize(keyword)
    conn = get_connection()

    row = conn.execute(
        "SELECT source FROM keywords WHERE keyword = ?", (keyword,)
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Keyword '{keyword}' not found")

    if row["source"] == "seed":
        conn.close()
        raise HTTPException(status_code=403, detail="Seed keywords cannot be removed")

    conn.execute("UPDATE keywords SET status = 'inactive' WHERE keyword = ?", (keyword,))
    conn.commit()
    conn.close()
    return {"message": f"Keyword '{keyword}' removed"}
