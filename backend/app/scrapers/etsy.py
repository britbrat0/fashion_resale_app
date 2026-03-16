import time
import random
import logging
from datetime import datetime, timezone

import requests
from app.config import settings
from app.database import get_connection

logger = logging.getLogger(__name__)

ETSY_BASE_URL = "https://openapi.etsy.com/v3/application/listings/active"

# Etsy taxonomy ID for Clothing (category)
CLOTHING_TAXONOMY_ID = 1


def scrape_etsy(keyword: str) -> bool:
    """Scrape Etsy active listings for a keyword. Returns True on success."""
    if not settings.etsy_api_key:
        logger.warning("Etsy API key not configured — skipping Etsy scraping")
        return True  # Not an error, just not configured

    try:
        headers = {
            "x-api-key": settings.etsy_api_key,
        }

        params = {
            "keywords": keyword,
            "taxonomy_id": CLOTHING_TAXONOMY_ID,
            "limit": 100,
            "sort_on": "score",
            "sort_order": "desc",
        }

        resp = requests.get(ETSY_BASE_URL, headers=headers, params=params, timeout=20)

        if resp.status_code == 429:
            logger.warning(f"Etsy API rate limited for '{keyword}', will retry later")
            return False

        if resp.status_code != 200:
            logger.warning(f"Etsy API returned {resp.status_code} for '{keyword}': {resp.text[:200]}")
            return False

        data = resp.json()
        results = data.get("results", [])
        total_count = data.get("count", 0)

        if not results:
            logger.warning(f"No Etsy listings found for '{keyword}'")
            return True

        prices = []
        quantities = []
        views_list = []
        tag_counts: dict[str, int] = {}

        for item in results:
            price_info = item.get("price", {})
            amount = price_info.get("amount")
            divisor = price_info.get("divisor", 100)
            if amount is not None:
                try:
                    price = float(amount) / float(divisor)
                    if 0 < price < 50000:
                        prices.append(price)
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            qty = item.get("quantity")
            if qty is not None:
                try:
                    quantities.append(int(qty))
                except (ValueError, TypeError):
                    pass

            views = item.get("views")
            if views is not None:
                try:
                    views_list.append(int(views))
                except (ValueError, TypeError):
                    pass

            for tag in item.get("tags", []):
                if isinstance(tag, str) and tag.strip():
                    t = tag.strip().lower()
                    tag_counts[t] = tag_counts.get(t, 0) + 1

        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()

        if prices:
            avg_price = sum(prices) / len(prices)
            conn.execute(
                "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
                (keyword, "etsy", "avg_price", avg_price, now),
            )

            # Price volatility (standard deviation)
            if len(prices) > 1:
                variance = sum((p - avg_price) ** 2 for p in prices) / (len(prices) - 1)
                volatility = variance ** 0.5
            else:
                volatility = 0.0

            conn.execute(
                "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
                (keyword, "etsy", "price_volatility", volatility, now),
            )

        # Listing count (total from API, not just this page)
        conn.execute(
            "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (keyword, "etsy", "listing_count", float(total_count), now),
        )

        # Total available quantity across sampled listings
        if quantities:
            conn.execute(
                "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
                (keyword, "etsy", "available_quantity", float(sum(quantities)), now),
            )

        # Views metrics
        if views_list:
            conn.execute(
                "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
                (keyword, "etsy", "avg_views", sum(views_list) / len(views_list), now),
            )
            conn.execute(
                "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
                (keyword, "etsy", "total_views", float(sum(views_list)), now),
            )

        # Tags — upsert frequency counts (top 50 by frequency)
        if tag_counts:
            top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:50]
            for tag, freq in top_tags:
                conn.execute(
                    """INSERT INTO keyword_tags (keyword, tag, frequency, scraped_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(keyword, tag) DO UPDATE SET
                           frequency = excluded.frequency,
                           scraped_at = excluded.scraped_at""",
                    (keyword, tag, freq, now),
                )

        conn.commit()
        conn.close()

        avg_str = f"${sum(prices)/len(prices):.2f}" if prices else "N/A"
        avg_views_str = f"{sum(views_list)/len(views_list):.0f}" if views_list else "N/A"
        logger.info(
            f"Etsy scrape complete for '{keyword}': {total_count} listings, "
            f"avg price {avg_str}, avg views {avg_views_str}, {len(tag_counts)} unique tags"
        )
        time.sleep(random.uniform(0.5, 1.5))
        return True

    except Exception as e:
        logger.error(f"Etsy scrape failed for '{keyword}': {e}")
        return False
