import time
import random
import logging
from datetime import datetime, timezone

from app.database import get_connection

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _sia = SentimentIntensityAnalyzer()
except ImportError:
    _sia = None

logger = logging.getLogger(__name__)

DEPOP_SEARCH_URL = "https://www.depop.com/search/?q={keyword}&location=us"


def scrape_depop(keyword: str) -> bool:
    """Scrape Depop search results using Playwright headless browser. Returns True on success."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        logger.error("Playwright not installed — skipping Depop scraping")
        return False

    url = DEPOP_SEARCH_URL.format(keyword=keyword.replace(" ", "+"))

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            page = context.new_page()

            # Block images/fonts to speed up loading
            page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda route: route.abort())

            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait for product listings to appear
            try:
                page.wait_for_selector("[class*='productCardRoot']", timeout=15000)
            except PlaywrightTimeout:
                logger.warning(f"Depop: no product cards found for '{keyword}' (timeout)")
                browser.close()
                return True

            # Small extra wait for prices to render
            page.wait_for_timeout(2000)

            # Extract prices from product cards
            prices = page.evaluate("""
                () => {
                    const prices = [];
                    const els = document.querySelectorAll('[class*="productAttributes"] p, [class*="Price"] p, [class*="price"] p');
                    for (const el of els) {
                        const text = el.textContent.trim();
                        const match = text.match(/\\$([\\d,]+\\.?\\d*)/);
                        if (match) {
                            const val = parseFloat(match[1].replace(',', ''));
                            if (val > 0 && val < 10000) prices.push(val);
                        }
                    }
                    return prices;
                }
            """)

            # Extract titles for sentiment
            titles = page.evaluate("""
                () => {
                    const titles = [];
                    const els = document.querySelectorAll('[class*="productCardRoot"] [class*="title"], [class*="productCardRoot"] p');
                    for (const el of els) {
                        const t = el.textContent.trim();
                        if (t.length > 4 && t.length < 120 && !t.startsWith('$')) titles.push(t);
                    }
                    return titles.slice(0, 100);
                }
            """)

            # Extract hashtags/tags if present
            raw_tags = page.evaluate("""
                () => {
                    const tags = [];
                    const els = document.querySelectorAll('[class*="tag"], [class*="Tag"], [class*="hashtag"], [class*="category"]');
                    for (const el of els) {
                        const t = el.textContent.trim().toLowerCase().replace(/^#/, '');
                        if (t.length > 1 && t.length < 50) tags.push(t);
                    }
                    return tags;
                }
            """)

            # Count product cards
            listing_count = page.evaluate("""
                () => document.querySelectorAll('[class*="productCardRoot"]').length
            """)

            browser.close()

        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()

        conn.execute(
            "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (keyword, "depop", "listing_count", float(listing_count), now),
        )

        if prices:
            avg_price = sum(prices) / len(prices)
            conn.execute(
                "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
                (keyword, "depop", "avg_price", avg_price, now),
            )
            if len(prices) > 1:
                variance = sum((p - avg_price) ** 2 for p in prices) / (len(prices) - 1)
                volatility = variance ** 0.5
                conn.execute(
                    "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
                    (keyword, "depop", "price_volatility", volatility, now),
                )

        # Title sentiment
        if _sia and titles:
            avg_sentiment = sum(_sia.polarity_scores(t)["compound"] for t in titles) / len(titles)
            conn.execute(
                "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)",
                (keyword, "depop", "sentiment_score", avg_sentiment, now),
            )

        # Tags
        if raw_tags:
            tag_counts: dict[str, int] = {}
            for t in raw_tags:
                tag_counts[t] = tag_counts.get(t, 0) + 1
            top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:30]
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
        logger.info(f"Depop scrape complete for '{keyword}': {listing_count} listings, avg {avg_str}")
        time.sleep(random.uniform(2, 4))
        return True

    except Exception as e:
        logger.error(f"Depop scrape failed for '{keyword}': {e}")
        return False


def discover_trending_keywords() -> list[str]:
    """Discover trending keywords from Depop using Playwright."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        return []

    candidates = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="en-US",
            )
            page = context.new_page()
            page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda route: route.abort())

            page.goto("https://www.depop.com/", wait_until="domcontentloaded", timeout=30000)

            try:
                page.wait_for_selector("[class*='trending'], [class*='Trending'], [class*='popular']", timeout=8000)
                terms = page.evaluate("""
                    () => {
                        const els = document.querySelectorAll('[class*="trending"] a, [class*="Trending"] a, [class*="popular"] a');
                        return Array.from(els).map(el => el.textContent.trim().toLowerCase()).filter(t => t.length > 2);
                    }
                """)
                candidates = list(set(terms))
            except PlaywrightTimeout:
                pass

            browser.close()

    except Exception as e:
        logger.error(f"Depop discovery failed: {e}")

    return candidates
