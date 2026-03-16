import logging
from datetime import datetime, timedelta, timezone

from app.database import get_connection

logger = logging.getLogger(__name__)

LIFECYCLE_STAGES = ["Emerging", "Accelerating", "Peak", "Saturation", "Decline", "Dormant"]


def _get_growth_rate(values_first_half: list[float], values_second_half: list[float]) -> float:
    """Calculate percentage growth between two halves of a time window.

    Uses a floor of 5 on the denominator to prevent astronomical percentages when a trend
    starts from near-zero on Google's relative 0-100 scale. Capped at ±500%.
    """
    if not values_first_half or not values_second_half:
        return 0.0
    avg_first = sum(values_first_half) / len(values_first_half)
    avg_second = sum(values_second_half) / len(values_second_half)
    denom = max(avg_first, 5.0)
    result = ((avg_second - denom) / denom) * 100
    return max(min(result, 500.0), -100.0)


def compute_composite_score(keyword: str, period_days: int) -> dict:
    """
    Compute composite trend score for a keyword over a time period.
    Returns dict with volume_growth, price_growth, composite_score, lifecycle_stage.
    """
    conn = get_connection()
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=period_days)
    midpoint = now - timedelta(days=period_days / 2)

    # Search volume growth (Google Trends 0-100 relative scale)
    vol_rows = conn.execute(
        "SELECT AVG(value) as value, DATE(recorded_at) as day FROM trend_data "
        "WHERE keyword = ? AND source = 'google_trends' AND metric = 'search_volume' "
        "AND recorded_at >= ? GROUP BY DATE(recorded_at) ORDER BY day",
        (keyword, start.isoformat()),
    ).fetchall()

    first_half_volumes = [r["value"] for r in vol_rows if r["day"] + "T00:00:00" < midpoint.isoformat()]
    second_half_volumes = [r["value"] for r in vol_rows if r["day"] + "T00:00:00" >= midpoint.isoformat()]
    volume_growth = _get_growth_rate(first_half_volumes, second_half_volumes)

    # Social mention growth (Reddit) — supplementary demand signal
    mention_rows = conn.execute(
        "SELECT AVG(value) as value, DATE(recorded_at) as day FROM trend_data "
        "WHERE keyword = ? AND source = 'reddit' AND metric = 'mention_count' "
        "AND recorded_at >= ? GROUP BY DATE(recorded_at) ORDER BY day",
        (keyword, start.isoformat()),
    ).fetchall()
    first_half_mentions = [r["value"] for r in mention_rows if r["day"] + "T00:00:00" < midpoint.isoformat()]
    second_half_mentions = [r["value"] for r in mention_rows if r["day"] + "T00:00:00" >= midpoint.isoformat()]
    mention_growth = _get_growth_rate(first_half_mentions, second_half_mentions)

    # Blend search volume with Reddit mentions when enough data exists (80/20)
    has_mention_data = len(mention_rows) >= 3
    demand_growth = (0.8 * volume_growth + 0.2 * mention_growth) if has_mention_data else volume_growth

    # Price growth: avg_price across all marketplaces
    price_rows = conn.execute(
        "SELECT value, recorded_at FROM trend_data WHERE keyword = ? AND source IN ('ebay', 'etsy', 'poshmark', 'depop') AND metric = 'avg_price' AND recorded_at >= ? ORDER BY recorded_at",
        (keyword, start.isoformat()),
    ).fetchall()
    first_half_prices = [r["value"] for r in price_rows if r["recorded_at"] < midpoint.isoformat()]
    second_half_prices = [r["value"] for r in price_rows if r["recorded_at"] >= midpoint.isoformat()]
    price_growth = _get_growth_rate(first_half_prices, second_half_prices)

    # Listing supply growth: listing_count across all marketplaces (supply pressure signal)
    listing_rows = conn.execute(
        "SELECT AVG(value) as value, DATE(recorded_at) as day FROM trend_data "
        "WHERE keyword = ? AND source IN ('ebay', 'etsy', 'poshmark', 'depop') AND metric = 'listing_count' "
        "AND recorded_at >= ? GROUP BY DATE(recorded_at) ORDER BY day",
        (keyword, start.isoformat()),
    ).fetchall()
    first_half_listings = [r["value"] for r in listing_rows if r["day"] + "T00:00:00" < midpoint.isoformat()]
    second_half_listings = [r["value"] for r in listing_rows if r["day"] + "T00:00:00" >= midpoint.isoformat()]
    listing_growth = _get_growth_rate(first_half_listings, second_half_listings)

    composite_score = 0.6 * demand_growth + 0.4 * price_growth

    scale_row = conn.execute(
        "SELECT scale FROM keywords WHERE keyword = ?", (keyword,)
    ).fetchone()
    scale = (scale_row["scale"] if scale_row and scale_row["scale"] else "macro")

    lifecycle_stage = _detect_lifecycle(keyword, demand_growth, composite_score, conn, start, scale, listing_growth)

    conn.close()

    return {
        "keyword": keyword,
        "period_days": period_days,
        "volume_growth": round(volume_growth, 2),
        "price_growth": round(price_growth, 2),
        "listing_growth": round(listing_growth, 2),
        "composite_score": round(composite_score, 2),
        "lifecycle_stage": lifecycle_stage,
        "scale": scale,
    }


def _detect_lifecycle(keyword: str, volume_growth: float, composite_score: float, conn, start, scale: str = "macro", listing_growth: float = 0.0) -> str:
    """Determine lifecycle stage based on volume levels, growth trajectory, and supply pressure.
    Scale-aware: micro trends use lower absolute volume thresholds."""
    volume_rows = conn.execute(
        "SELECT SUM(avg_val) as total FROM ("
        "  SELECT AVG(value) as avg_val FROM trend_data "
        "  WHERE keyword = ? AND source = 'google_trends' AND metric = 'search_volume' AND recorded_at >= ? "
        "  GROUP BY DATE(recorded_at)"
        ")",
        (keyword, start.isoformat()),
    ).fetchone()

    total_volume = volume_rows["total"] if volume_rows["total"] else 0

    prev_scores = conn.execute(
        "SELECT composite_score FROM trend_scores WHERE keyword = ? ORDER BY computed_at DESC LIMIT 3",
        (keyword,),
    ).fetchall()
    prev_score_values = [r["composite_score"] for r in prev_scores if r["composite_score"] is not None]
    acceleration = (composite_score - prev_score_values[0]) if len(prev_score_values) >= 2 else 0

    # Supply pressure: listings growing significantly faster than demand (supply > demand signal)
    # Only meaningful when we actually have listing data (listing_growth != 0)
    supply_pressure = (
        listing_growth > 5.0
        and listing_growth > max(volume_growth, 0) * 1.5
    )

    # Micro trends operate at much lower absolute volumes
    is_micro = scale == "micro"
    dormant_thresh = 2 if is_micro else 5
    emerging_vol_thresh = 15 if is_micro else 100
    peak_vol_thresh = 5 if is_micro else 50

    if total_volume < dormant_thresh:
        return "Dormant"
    elif volume_growth > 30 and total_volume < emerging_vol_thresh:
        return "Emerging"
    elif volume_growth > 20 and acceleration > 0 and not supply_pressure:
        return "Accelerating"
    elif -5 <= volume_growth <= 10 and total_volume > peak_vol_thresh:
        # Supply flooding the market can push a flat-volume trend into Saturation early
        if supply_pressure and acceleration <= 0:
            return "Saturation"
        if acceleration <= 0:
            return "Peak"
        return "Accelerating"
    elif -20 <= volume_growth < -5 or supply_pressure:
        return "Saturation"
    elif volume_growth < -20:
        return "Decline"
    else:
        if volume_growth > 10:
            return "Emerging"
        return "Peak"


def predict_stage_warning(current_stage: str, current_vg: float, projected_vg: float, slope: float) -> str | None:
    """Return a human-readable warning if the trend is likely to transition lifecycle stages
    within the next 7 days, or None if the stage looks stable."""
    if current_stage == "Emerging" and projected_vg > 30 and slope > 1.5:
        return "Approaching Accelerating"
    if current_stage == "Accelerating" and slope > 2.0 and projected_vg > 45:
        return "Nearing Peak"
    if current_stage == "Accelerating" and slope < -1.5:
        return "Growth slowing"
    if current_stage == "Peak" and slope < -1.5:
        return "Entering Saturation"
    if current_stage == "Saturation" and slope < -2.5:
        return "Approaching Decline"
    if current_stage == "Decline" and slope < -3.5:
        return "Nearing Dormant"
    if current_stage == "Dormant" and slope > 1.5:
        return "Signs of Revival"
    return None


def compute_and_store_scores(keyword: str):
    """Compute scores for all standard time periods and store in trend_scores."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()

    for period in [7, 14, 30, 60, 90]:
        result = compute_composite_score(keyword, period)

        # Delete old score for this keyword + period
        conn.execute(
            "DELETE FROM trend_scores WHERE keyword = ? AND period_days = ?",
            (keyword, period),
        )

        conn.execute(
            "INSERT INTO trend_scores (keyword, period_days, volume_growth, price_growth, listing_growth, composite_score, lifecycle_stage, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (keyword, period, result["volume_growth"], result["price_growth"], result["listing_growth"], result["composite_score"], result["lifecycle_stage"], now),
        )

    conn.commit()
    conn.close()


def get_top_trends(period_days: int = 7, limit: int = 10, user_email: str = None) -> list[dict]:
    """Get top N trends ranked by composite score for a given period.
    Authenticated users see seed keywords + their own; guests see seed keywords only."""
    conn = get_connection()
    if user_email:
        rows = conn.execute(
            """SELECT ts.keyword, ts.composite_score, ts.volume_growth, ts.price_growth,
                      ts.lifecycle_stage, ts.computed_at, k.source, COALESCE(k.scale, 'macro') as scale
               FROM trend_scores ts
               LEFT JOIN keywords k ON ts.keyword = k.keyword
               LEFT JOIN user_keywords uk ON ts.keyword = uk.keyword AND uk.user_email = ?
               WHERE ts.period_days = ? AND (k.status IS NULL OR k.status != 'inactive')
               AND (
                   k.source = 'seed'
                   OR uk.keyword IS NOT NULL
                   OR (k.source = 'user_search'
                       AND NOT EXISTS (SELECT 1 FROM user_keywords uk2 WHERE uk2.keyword = ts.keyword))
               )
               ORDER BY ts.composite_score DESC""",
            (user_email, period_days),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT ts.keyword, ts.composite_score, ts.volume_growth, ts.price_growth,
                      ts.lifecycle_stage, ts.computed_at, k.source, COALESCE(k.scale, 'macro') as scale
               FROM trend_scores ts LEFT JOIN keywords k ON ts.keyword = k.keyword
               WHERE ts.period_days = ? AND (k.status IS NULL OR k.status != 'inactive')
               AND k.source = 'seed'
               ORDER BY ts.composite_score DESC""",
            (period_days,),
        ).fetchall()
    conn.close()

    all_trends = [dict(r) for r in rows]

    macro = sorted([t for t in all_trends if t["scale"] == "macro"], key=lambda t: t["composite_score"] or 0, reverse=True)
    micro = sorted([t for t in all_trends if t["scale"] == "micro"], key=lambda t: t["composite_score"] or 0, reverse=True)

    def assign_percentile(group):
        n = len(group)
        for i, t in enumerate(group):
            t["_pct"] = (n - i) / n if n > 0 else 0.5
        return group

    combined = sorted(
        assign_percentile(macro) + assign_percentile(micro),
        key=lambda t: t["_pct"],
        reverse=True,
    )

    return [
        {
            "rank": i + 1,
            "keyword": t["keyword"],
            "composite_score": t["composite_score"],
            "volume_growth": t["volume_growth"],
            "price_growth": t["price_growth"],
            "lifecycle_stage": t["lifecycle_stage"],
            "computed_at": t["computed_at"],
            "source": t["source"] or "seed",
            "scale": t["scale"],
        }
        for i, t in enumerate(combined[:limit])
    ]


def get_keyword_details(keyword: str, period_days: int = 7) -> dict:
    """Get full trend detail for a keyword: time series, price, volume, volatility, regions."""
    conn = get_connection()
    start = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()

    # Score
    score_row = conn.execute(
        "SELECT * FROM trend_scores WHERE keyword = ? AND period_days = ? ORDER BY computed_at DESC LIMIT 1",
        (keyword, period_days),
    ).fetchone()

    # Search volume over time
    search_volume = conn.execute(
        "SELECT value, recorded_at FROM trend_data WHERE keyword = ? AND source = 'google_trends' AND metric = 'search_volume' AND recorded_at >= ? ORDER BY recorded_at",
        (keyword, start),
    ).fetchall()

    # Fallback: if no data in the selected period, show whatever recent data exists
    search_volume_stale = False
    if not search_volume:
        fallback_rows = conn.execute(
            "SELECT value, recorded_at FROM trend_data "
            "WHERE keyword = ? AND source = 'google_trends' AND metric = 'search_volume' "
            "ORDER BY recorded_at DESC LIMIT 90",
            (keyword,),
        ).fetchall()
        if fallback_rows:
            search_volume = list(reversed(fallback_rows))
            search_volume_stale = True

    # Avg price over time — one point per day, averaged across all marketplace sources
    ebay_prices = conn.execute(
        "SELECT AVG(value) as value, DATE(recorded_at) as recorded_at FROM trend_data "
        "WHERE keyword = ? AND source IN ('ebay', 'etsy', 'poshmark', 'depop') AND metric = 'avg_price' AND recorded_at >= ? "
        "GROUP BY DATE(recorded_at) ORDER BY recorded_at",
        (keyword, start),
    ).fetchall()

    # Sales/listing volume over time — one point per day, summed across sources
    sales_volume = conn.execute(
        "SELECT SUM(value) as value, DATE(recorded_at) as recorded_at FROM trend_data "
        "WHERE keyword = ? AND source IN ('ebay', 'etsy', 'poshmark', 'depop') AND metric IN ('sold_count', 'listing_count') AND recorded_at >= ? "
        "GROUP BY DATE(recorded_at) ORDER BY recorded_at",
        (keyword, start),
    ).fetchall()

    # Price volatility (latest from any source)
    volatility = conn.execute(
        "SELECT value, recorded_at FROM trend_data WHERE keyword = ? AND source IN ('ebay', 'etsy', 'poshmark', 'depop') AND metric = 'price_volatility' AND recorded_at >= ? ORDER BY recorded_at DESC LIMIT 1",
        (keyword, start),
    ).fetchone()

    # Region data — US
    us_regions = conn.execute(
        "SELECT region, value FROM trend_data WHERE keyword = ? AND metric = 'search_volume_region' AND recorded_at >= ? ORDER BY value DESC",
        (keyword, start),
    ).fetchall()

    # Region data — global
    global_regions = conn.execute(
        "SELECT region, value FROM trend_data WHERE keyword = ? AND metric = 'search_volume_region_global' AND recorded_at >= ? ORDER BY value DESC",
        (keyword, start),
    ).fetchall()

    # eBay listing sentiment history
    ebay_sentiment_rows = conn.execute(
        "SELECT value, recorded_at FROM trend_data WHERE keyword = ? AND source = 'ebay' AND metric = 'sentiment_score' AND recorded_at >= ? ORDER BY recorded_at",
        (keyword, start),
    ).fetchall()

    # Reddit mentions + sentiment history
    reddit_mention_rows = conn.execute(
        "SELECT value, recorded_at FROM trend_data WHERE keyword = ? AND source = 'reddit' AND metric = 'mention_count' AND recorded_at >= ? ORDER BY recorded_at",
        (keyword, start),
    ).fetchall()
    reddit_sentiment_rows = conn.execute(
        "SELECT value, recorded_at FROM trend_data WHERE keyword = ? AND source = 'reddit' AND metric = 'sentiment_score' AND recorded_at >= ? ORDER BY recorded_at",
        (keyword, start),
    ).fetchall()

    # TikTok mentions + sentiment history
    tiktok_mention_rows = conn.execute(
        "SELECT value, recorded_at FROM trend_data WHERE keyword = ? AND source = 'tiktok' AND metric = 'tiktok_mentions' AND recorded_at >= ? ORDER BY recorded_at",
        (keyword, start),
    ).fetchall()
    tiktok_sentiment_rows = conn.execute(
        "SELECT value, recorded_at FROM trend_data WHERE keyword = ? AND source = 'tiktok' AND metric = 'tiktok_sentiment' AND recorded_at >= ? ORDER BY recorded_at",
        (keyword, start),
    ).fetchall()

    # News article mentions + sentiment
    news_mention_rows = conn.execute(
        "SELECT value, recorded_at FROM trend_data WHERE keyword = ? AND source = 'news' AND metric = 'news_mentions' AND recorded_at >= ? ORDER BY recorded_at",
        (keyword, start),
    ).fetchall()
    news_sentiment_rows = conn.execute(
        "SELECT value, recorded_at FROM trend_data WHERE keyword = ? AND source = 'news' AND metric = 'news_sentiment' AND recorded_at >= ? ORDER BY recorded_at",
        (keyword, start),
    ).fetchall()

    # Sell-through: latest active listing count + latest 30d sold count
    latest_active = conn.execute(
        "SELECT value FROM trend_data WHERE keyword = ? AND source = 'ebay' AND metric = 'sold_count' ORDER BY recorded_at DESC LIMIT 1",
        (keyword,),
    ).fetchone()
    latest_sold = conn.execute(
        "SELECT value FROM trend_data WHERE keyword = ? AND source = 'ebay' AND metric = 'sold_count_30d' ORDER BY recorded_at DESC LIMIT 1",
        (keyword,),
    ).fetchone()

    conn.close()

    sell_through = None
    if latest_active and latest_sold:
        active_val = latest_active["value"]
        sold_val = latest_sold["value"]
        total = active_val + sold_val
        rate = (sold_val / total * 100.0) if total > 0 else None
        sell_through = {
            "sold_30d": int(sold_val),
            "active": int(active_val),
            "rate": round(rate, 1) if rate is not None else None,
        }

    # Coefficient of variation: std_dev / avg_price * 100, so the volatility label is
    # relative to the item's price rather than an absolute dollar threshold.
    volatility_val = volatility["value"] if volatility else None
    all_price_values = [r["value"] for r in ebay_prices if r["value"] and r["value"] > 0]
    overall_avg_price = sum(all_price_values) / len(all_price_values) if all_price_values else None
    volatility_cv = (
        round(volatility_val / overall_avg_price * 100, 1)
        if volatility_val and overall_avg_price and overall_avg_price > 0
        else None
    )

    return {
        "keyword": keyword,
        "period_days": period_days,
        "score": dict(score_row) if score_row else None,
        "search_volume": [{"value": r["value"], "date": r["recorded_at"]} for r in search_volume],
        "search_volume_stale": search_volume_stale,
        "ebay_avg_price": [{"value": r["value"], "date": r["recorded_at"]} for r in ebay_prices],
        "sales_volume": [{"value": r["value"], "date": r["recorded_at"]} for r in sales_volume],
        "price_volatility": volatility_val,
        "price_volatility_cv": volatility_cv,
        "regions_us": [{"region": r["region"], "value": r["value"]} for r in us_regions],
        "regions_global": [{"region": r["region"], "value": r["value"]} for r in global_regions],
        "ebay_sentiment": [{"date": r["recorded_at"], "value": r["value"]} for r in ebay_sentiment_rows],
        "social_mentions": {
            "reddit": [{"date": r["recorded_at"], "count": r["value"]} for r in reddit_mention_rows],
            "reddit_sentiment": [{"date": r["recorded_at"], "value": r["value"]} for r in reddit_sentiment_rows],
            "tiktok": [{"date": r["recorded_at"], "count": r["value"]} for r in tiktok_mention_rows],
            "tiktok_sentiment": [{"date": r["recorded_at"], "value": r["value"]} for r in tiktok_sentiment_rows],
            "news": [{"date": r["recorded_at"], "count": r["value"]} for r in news_mention_rows],
            "news_sentiment": [{"date": r["recorded_at"], "value": r["value"]} for r in news_sentiment_rows],
        },
        "sell_through": sell_through,
    }
