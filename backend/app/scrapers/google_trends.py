import time
import random
import logging
from datetime import datetime, timedelta, timezone

from pytrends.request import TrendReq
from app.database import get_connection

logger = logging.getLogger(__name__)

# Global rate-limit cooldown — set when a 429 is detected; all scrape calls are
# skipped until the cooldown expires. This prevents burning retries across every
# keyword in the queue when Google Trends is actively blocking requests.
_COOLDOWN_HOURS = 2
_rate_limit_until: datetime | None = None


def _is_rate_limited() -> bool:
    global _rate_limit_until
    if _rate_limit_until is None:
        return False
    if datetime.now(timezone.utc) < _rate_limit_until:
        return True
    _rate_limit_until = None
    return False


def _activate_cooldown():
    global _rate_limit_until
    _rate_limit_until = datetime.now(timezone.utc) + timedelta(hours=_COOLDOWN_HOURS)
    logger.warning(
        f"Google Trends: 429 detected — activating {_COOLDOWN_HOURS}h global cooldown "
        f"(until {_rate_limit_until.strftime('%H:%M UTC')})"
    )


class _RateLimitError(Exception):
    pass


def scrape_google_trends(keyword: str, retries: int = 3) -> bool:
    """Scrape Google Trends for a keyword. Returns True on success.
    On 429, activates a 2-hour global cooldown and returns False immediately."""
    if _is_rate_limited():
        logger.warning(f"Google Trends: skipping '{keyword}' — cooldown active until {_rate_limit_until.strftime('%H:%M UTC')}")
        return False

    for attempt in range(retries):
        try:
            result = _scrape_google_trends_once(keyword)
        except _RateLimitError:
            _activate_cooldown()
            return False
        if result:
            return True
        wait = 60 * (2 ** attempt)  # 60s, 120s, 240s
        logger.warning(f"Google Trends failed for '{keyword}', retrying in {wait}s (attempt {attempt + 1}/{retries})")
        time.sleep(wait)
    logger.error(f"Google Trends scrape failed for '{keyword}' after {retries} attempts")
    return False


def _has_recent_region_data(keyword: str, metric: str, days: int = 14) -> bool:
    """Return True if we already have recent regional data for this keyword."""
    threshold = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM trend_data WHERE keyword = ? AND source = 'google_trends' AND metric = ? AND recorded_at >= ? LIMIT 1",
        (keyword, metric, threshold),
    ).fetchone()
    conn.close()
    return row is not None


def _scrape_google_trends_once(keyword: str) -> bool:
    """Single attempt to scrape Google Trends for a keyword."""
    try:
        pytrends = TrendReq(hl="en-US", tz=360)
        pytrends.build_payload([keyword], timeframe="today 3-m", geo="US")

        # Interest over time
        interest_df = pytrends.interest_over_time()
        if not interest_df.empty and keyword in interest_df.columns:
            conn = get_connection()
            for date, row in interest_df.iterrows():
                date_str = date.strftime("%Y-%m-%dT00:00:00")
                value = float(row[keyword])
                existing = conn.execute(
                    "SELECT rowid, value FROM trend_data WHERE keyword = ? AND source = 'google_trends' AND metric = 'search_volume' AND recorded_at = ? AND region IS NULL",
                    (keyword, date_str),
                ).fetchone()
                if existing:
                    if existing["value"] == 0.0 or value > existing["value"]:
                        conn.execute("UPDATE trend_data SET value = ? WHERE rowid = ?", (value, existing["rowid"]))
                else:
                    conn.execute(
                        "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
                        (keyword, "google_trends", "search_volume", value, date_str),
                    )
            conn.commit()
            conn.close()

        # Regional data: skip if already fresh (saves 2 of the 3 pytrends calls when data is current)
        skip_regions = (
            _has_recent_region_data(keyword, "search_volume_region", days=14) and
            _has_recent_region_data(keyword, "search_volume_region_global", days=14)
        )

        if not skip_regions:
            time.sleep(random.uniform(8, 15))

            # US state breakdown
            try:
                pytrends.build_payload([keyword], timeframe="today 3-m", geo="US")
                region_df = pytrends.interest_by_region(resolution="REGION", inc_low_vol=True)
                if not region_df.empty and keyword in region_df.columns:
                    conn = get_connection()
                    now = datetime.now(timezone.utc).isoformat()
                    for region, row in region_df.iterrows():
                        if row[keyword] > 0:
                            conn.execute(
                                "INSERT OR IGNORE INTO trend_data (keyword, source, metric, value, region, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
                                (keyword, "google_trends", "search_volume_region", float(row[keyword]), region, now),
                            )
                    conn.commit()
                    conn.close()
            except Exception as e:
                logger.warning(f"Failed to get US region data for '{keyword}': {e}")

            time.sleep(random.uniform(8, 15))

            # Global country breakdown
            try:
                pytrends.build_payload([keyword], timeframe="today 3-m")
                world_df = pytrends.interest_by_region(resolution="COUNTRY", inc_low_vol=True)
                if not world_df.empty and keyword in world_df.columns:
                    conn = get_connection()
                    now = datetime.now(timezone.utc).isoformat()
                    for country, row in world_df.iterrows():
                        if row[keyword] > 0:
                            conn.execute(
                                "INSERT OR IGNORE INTO trend_data (keyword, source, metric, value, region, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
                                (keyword, "google_trends", "search_volume_region_global", float(row[keyword]), country, now),
                            )
                    conn.commit()
                    conn.close()
            except Exception as e:
                logger.warning(f"Failed to get global region data for '{keyword}': {e}")
        else:
            logger.debug(f"Google Trends: skipping regional calls for '{keyword}' — data is fresh")

        logger.info(f"Google Trends scrape complete for '{keyword}' (regions {'skipped' if skip_regions else 'updated'})")
        return True

    except Exception as e:
        msg = str(e)
        if "429" in msg or "Too Many Requests" in msg.lower() or "response code" in msg.lower() and "429" in msg:
            raise _RateLimitError(msg)
        logger.error(f"Google Trends scrape failed for '{keyword}': {e}")
        return False
