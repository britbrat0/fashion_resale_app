import base64
import time
import random
import logging
from datetime import datetime, timezone

import requests
from app.config import settings
from app.database import get_connection

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _sia = SentimentIntensityAnalyzer()
except ImportError:
    _sia = None

logger = logging.getLogger(__name__)

EBAY_FINDING_URL = "https://svcs.ebay.com/services/search/FindingService/v1"

# eBay OAuth token endpoint (sandbox if keys contain SBX, else production)
EBAY_AUTH_URL_PROD = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_AUTH_URL_SANDBOX = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"

EBAY_BROWSE_URL_PROD = "https://api.ebay.com/buy/browse/v1/item_summary/search"
EBAY_BROWSE_URL_SANDBOX = "https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search"


def _is_sandbox() -> bool:
    return "SBX" in (settings.ebay_app_id or "")


EBAY_SCOPE_PROD = "https://api.ebay.com/oauth/api_scope"
EBAY_SCOPE_SANDBOX = "https://api.sandbox.ebay.com/oauth/api_scope"

_cached_token = {"token": None, "expires_at": 0}


def _get_oauth_token() -> str | None:
    """Get an eBay OAuth application access token using client credentials."""
    if not settings.ebay_app_id or not settings.ebay_cert_id:
        logger.warning("eBay API credentials not configured — skipping eBay scraping")
        return None

    # Check cache
    now = time.time()
    if _cached_token["token"] and _cached_token["expires_at"] > now + 60:
        return _cached_token["token"]

    try:
        credentials = base64.b64encode(
            f"{settings.ebay_app_id}:{settings.ebay_cert_id}".encode()
        ).decode()

        sandbox = _is_sandbox()
        auth_url = EBAY_AUTH_URL_SANDBOX if sandbox else EBAY_AUTH_URL_PROD
        scope = EBAY_SCOPE_SANDBOX if sandbox else EBAY_SCOPE_PROD

        resp = requests.post(
            auth_url,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {credentials}",
            },
            data={
                "grant_type": "client_credentials",
                "scope": scope,
            },
            timeout=15,
        )
        resp.raise_for_status()

        data = resp.json()
        token = data["access_token"]
        expires_in = data.get("expires_in", 7200)

        _cached_token["token"] = token
        _cached_token["expires_at"] = now + expires_in

        logger.info("eBay OAuth token obtained successfully")
        return token

    except Exception as e:
        logger.error(f"Failed to get eBay OAuth token: {e}")
        return None


def scrape_ebay(keyword: str) -> bool:
    """Scrape eBay listings for a keyword using the Browse API. Returns True on success."""
    token = _get_oauth_token()
    if token is None:
        return True  # Not an error, just not configured

    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            "X-EBAY-C-ENDUSERCTX": "affiliateCampaignId=<ePNCampaignId>,affiliateReferenceId=<referenceId>",
        }

        # Search for items in Clothing, Shoes & Accessories (category 11450)
        params = {
            "q": keyword,
            "category_ids": "11450",
            "limit": "50",
            "sort": "newlyListed",
            "filter": "buyingOptions:{FIXED_PRICE|AUCTION}",
            "fieldgroups": "EXTENDED",
        }

        browse_url = EBAY_BROWSE_URL_SANDBOX if _is_sandbox() else EBAY_BROWSE_URL_PROD

        resp = requests.get(browse_url, headers=headers, params=params, timeout=20)

        if resp.status_code == 401:
            # Token expired, clear cache and retry once
            _cached_token["token"] = None
            token = _get_oauth_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
                resp = requests.get(browse_url, headers=headers, params=params, timeout=20)

        if resp.status_code != 200:
            logger.warning(f"eBay Browse API returned {resp.status_code} for '{keyword}': {resp.text[:200]}")
            return False

        data = resp.json()
        items = data.get("itemSummaries", [])

        if not items:
            logger.warning(f"No eBay items found for '{keyword}'")
            return True

        prices = []
        titles = []
        watch_counts = []
        images_to_store = []
        tag_counts: dict[str, int] = {}

        for item in items:
            price_info = item.get("price", {})
            value = price_info.get("value")
            item_price = None
            if value:
                try:
                    item_price = float(value)
                    if 0 < item_price < 50000:
                        prices.append(item_price)
                except (ValueError, TypeError):
                    pass

            image_url = item.get("image", {}).get("imageUrl")
            item_url = item.get("itemWebUrl")
            title = item.get("title")
            if title:
                titles.append(title)
            if image_url and len(images_to_store) < 6:
                images_to_store.append((keyword, "ebay", image_url, title, item_price, item_url))

            watch = item.get("watchCount")
            if watch is not None:
                try:
                    watch_counts.append(int(watch))
                except (ValueError, TypeError):
                    pass

            # localizedAspects available with fieldgroups=EXTENDED
            for aspect in item.get("localizedAspects", []):
                tag = aspect.get("value", "").strip().lower()
                if tag and len(tag) < 60:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

        if not prices:
            logger.warning(f"No parseable eBay prices for '{keyword}'")
            return True

        now = datetime.now(timezone.utc).isoformat()
        avg_price = sum(prices) / len(prices)
        listing_count = len(items)

        # Price volatility (standard deviation)
        if len(prices) > 1:
            mean = avg_price
            variance = sum((p - mean) ** 2 for p in prices) / (len(prices) - 1)
            volatility = variance ** 0.5
        else:
            volatility = 0.0

        conn = get_connection()
        conn.execute(
            "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (keyword, "ebay", "avg_price", avg_price, now),
        )
        conn.execute(
            "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (keyword, "ebay", "listing_count", float(listing_count), now),
        )
        conn.execute(
            "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (keyword, "ebay", "price_volatility", volatility, now),
        )

        # Watch count (demand/interest signal)
        if watch_counts:
            conn.execute(
                "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
                (keyword, "ebay", "avg_watch_count", sum(watch_counts) / len(watch_counts), now),
            )
            conn.execute(
                "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
                (keyword, "ebay", "total_watch_count", float(sum(watch_counts)), now),
            )

        # Tags from localizedAspects (top 50 by frequency)
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

        # Title sentiment
        if _sia and titles:
            avg_sentiment = sum(_sia.polarity_scores(t)["compound"] for t in titles) / len(titles)
            conn.execute(
                "INSERT OR IGNORE INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
                (keyword, "ebay", "sentiment_score", avg_sentiment, now),
            )

        for img in images_to_store:
            conn.execute(
                "INSERT OR IGNORE INTO trend_images (keyword, source, image_url, title, price, item_url) VALUES (?, ?, ?, ?, ?, ?)",
                img,
            )

        # Prune to 8 most recent images per keyword
        conn.execute(
            """DELETE FROM trend_images WHERE keyword = ? AND id NOT IN (
                SELECT id FROM trend_images WHERE keyword = ? ORDER BY scraped_at DESC LIMIT 8
            )""",
            (keyword, keyword),
        )

        conn.commit()
        conn.close()

        watch_str = f"{sum(watch_counts)/len(watch_counts):.0f}" if watch_counts else "N/A"
        logger.info(
            f"eBay API scrape complete for '{keyword}': {listing_count} listings, "
            f"avg ${avg_price:.2f}, avg watches {watch_str}, {len(tag_counts)} unique aspects"
        )

        # Non-fatal: also fetch sold counts via Finding API
        try:
            scrape_ebay_sold(keyword)
        except Exception as e:
            logger.warning(f"eBay sold count scrape failed for '{keyword}': {e}")

        time.sleep(random.uniform(0.5, 1.5))
        return True

    except Exception as e:
        logger.error(f"eBay API scrape failed for '{keyword}': {e}")
        return False


def scrape_ebay_sold(keyword: str) -> bool:
    """Fetch sold item count from eBay Finding API to support sell-through rate calculation."""
    if not settings.ebay_app_id:
        return False

    params = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": settings.ebay_app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "",
        "keywords": keyword,
        "categoryId": "11450",
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "paginationInput.entriesPerPage": "100",
    }

    resp = requests.get(
        EBAY_FINDING_URL,
        params=params,
        headers={"X-EBAY-SOA-SECURITY-APPNAME": settings.ebay_app_id},
        timeout=20,
    )

    if resp.status_code != 200:
        logger.warning(f"eBay Finding API returned {resp.status_code} for '{keyword}'")
        return False

    data = resp.json()
    try:
        result = data.get("findCompletedItemsResponse", [{}])[0]
        items = result.get("searchResult", [{}])[0].get("item", [])
        count = float(len(items))
    except (KeyError, IndexError, TypeError):
        count = 0.0

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
        (keyword, "ebay", "sold_count_30d", count, now),
    )
    conn.commit()
    conn.close()

    logger.info(f"eBay sold count for '{keyword}': {count}")
    return True
