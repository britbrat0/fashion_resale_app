import json
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

from app.database import get_connection
from app.vintage.router import _ERAS, _ERA_BY_ID

logger = logging.getLogger(__name__)

SAMPLES_PER_ERA = 20
_MIN_SAMPLES_FOR_ACCURACY = 5


# ── Requests-based Etsy scraper ────────────────────────────────────────────────

def _scrape_etsy_requests(query: str, limit: int = 6) -> list[dict]:
    """Scrape Etsy search results via requests + BeautifulSoup. Returns [{title, price, url}]."""
    import requests
    from bs4 import BeautifulSoup

    url = f"https://www.etsy.com/search?q={quote_plus(query)}&explicit=1"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        logger.info(f"Etsy requests: status={resp.status_code} for '{query}'")
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[dict] = []

        # ── Try JSON-LD structured data first ────────────────────────────────
        for script in soup.find_all("script", type="application/ld+json"):
            if len(results) >= limit:
                break
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict) and data.get("@type") == "ItemList":
                    for item in data.get("itemListElement", []):
                        if len(results) >= limit:
                            break
                        offer = item.get("item") or {}
                        name = offer.get("name", "").strip()
                        item_url = offer.get("url", "").strip()
                        price = None
                        offers = offer.get("offers") or {}
                        if isinstance(offers, dict) and offers.get("price"):
                            try:
                                price = round(float(offers["price"]), 2)
                            except (ValueError, TypeError):
                                pass
                        if name and item_url:
                            results.append({"title": name, "price": price, "url": item_url})
            except Exception:
                pass

        if results:
            logger.info(f"Etsy requests (JSON-LD): {len(results)} listings for '{query}'")
            return results

        # ── Fallback: parse anchor tags ────────────────────────────────────────
        seen: set[str] = set()
        for link in soup.select("a[href*='/listing/']"):
            if len(results) >= limit:
                break
            href = link.get("href", "")
            if not href or "/listing/" not in href:
                continue
            if not href.startswith("http"):
                href = "https://www.etsy.com" + href
            clean_href = href.split("?")[0]
            if clean_href in seen:
                continue
            seen.add(clean_href)

            title = None
            img = link.find("img")
            if img:
                title = (img.get("alt") or "").strip()
            if not title:
                title = (link.get("aria-label") or "").strip()
            if not title:
                title = link.get_text(" ", strip=True)[:200]
            if not title:
                continue

            price = None
            container = link.parent
            if container:
                m = re.search(r"\$\s*([\d,]+\.?\d*)", container.get_text())
                if m:
                    price = round(float(m.group(1).replace(",", "")), 2)

            results.append({"title": title, "price": price, "url": href})

        logger.info(f"Etsy requests (HTML): {len(results)} listings for '{query}'")
        return results

    except Exception as e:
        logger.error(f"Etsy requests scrape failed for '{query}': {e}")
        return []


# ── Playwright Etsy scraper (kept for validation collection only) ──────────────

def _scrape_etsy_playwright(query: str, limit: int = 6) -> list[dict]:
    """Scrape Etsy search results via Playwright. Returns [{title, price, url}]."""
    try:
        from playwright.sync_api import sync_playwright

        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--window-size=1280,900",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            page = context.new_page()
            # Hide automation markers
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
                window.chrome = {runtime: {}};
            """)
            page.route("**/*.{woff,woff2,ttf,otf,mp4,webm,ogg,mp3}", lambda r: r.abort())

            url = f"https://www.etsy.com/search?q={quote_plus(query)}&explicit=1"
            try:
                page.goto(url, timeout=25000, wait_until="domcontentloaded")
            except Exception as e:
                logger.warning(f"Etsy page load failed for '{query}': {e}")
                browser.close()
                return []

            logger.info(f"Etsy page loaded for '{query}': url={page.url[:80]} title={page.title()[:60]}")

            if "signin" in page.url or "join" in page.url:
                logger.warning(f"Etsy redirected to login for '{query}'")
                browser.close()
                return []

            # Dismiss cookie/GDPR banner if present
            try:
                accept = page.query_selector("button[data-gdpr-single-choice-accept], button[id*='accept'], button[class*='accept-cookies']")
                if accept:
                    accept.click()
                    page.wait_for_timeout(500)
            except Exception:
                pass

            # Wait for listing links — more reliable than specific card attrs
            try:
                page.wait_for_selector("a[href*='/listing/']", timeout=12000)
            except Exception:
                logger.warning(f"Etsy: no listing links found for '{query}' (title: {page.title()[:60]})")
                browser.close()
                return []

            page.evaluate("window.scrollBy(0, 800)")
            page.wait_for_timeout(1200)

            # Collect all listing links, deduplicated
            links = page.query_selector_all("a[href*='/listing/']")
            logger.info(f"Etsy: found {len(links)} listing links for '{query}'")

            seen_urls: set[str] = set()
            for link in links:
                if len(results) >= limit:
                    break

                href = link.get_attribute("href") or ""
                if not href or href in seen_urls:
                    continue
                # Skip non-listing links (cart, etc.)
                if "/listing/" not in href:
                    continue
                if not href.startswith("http"):
                    href = "https://www.etsy.com" + href
                # Strip query params to dedup
                clean_href = href.split("?")[0]
                if clean_href in seen_urls:
                    continue
                seen_urls.add(clean_href)

                # Title: try img alt, then aria-label, then inner text of the link
                title = None
                img = link.query_selector("img")
                if img:
                    title = (img.get_attribute("alt") or "").strip()
                if not title:
                    title = (link.get_attribute("aria-label") or "").strip()
                if not title:
                    title = link.inner_text().strip()[:200]
                if not title:
                    continue

                # Price: look for $ near the link's parent container
                price = None
                try:
                    container = link.evaluate_handle(
                        "el => el.closest('li') || el.closest('[data-listing-id]') || el.parentElement"
                    ).as_element()
                    if container:
                        text = container.inner_text()
                        m = re.search(r'\$\s*([\d,]+\.?\d*)', text)
                        if m:
                            price = round(float(m.group(1).replace(",", "")), 2)
                except Exception:
                    pass

                results.append({"title": title, "price": price, "url": href})

            browser.close()

        logger.info(f"Etsy Playwright: returning {len(results)} listings for '{query}'")
        return results

    except Exception as e:
        logger.error(f"Etsy Playwright scrape failed for '{query}': {e}")
        return []


def search_etsy_listings(keyword: str, limit: int = 6) -> list[dict]:
    """Return live Etsy listings for a keyword. Tries requests first, falls back to Playwright."""
    results = _scrape_etsy_requests(keyword, limit=limit)
    if not results:
        results = _scrape_etsy_playwright(keyword, limit=limit)
    return results


# ── Era helpers ────────────────────────────────────────────────────────────────

def _era_decade(era_id: str) -> str | None:
    era = _ERA_BY_ID.get(era_id)
    if not era:
        return None
    return f"{(era['start_year'] // 10) * 10}s"


# ── Validation data collection ─────────────────────────────────────────────────

def collect_era_samples(era_id: str, target: int = SAMPLES_PER_ERA) -> int:
    """Scrape Etsy for vintage listings matching an era's decade, store as validation items."""
    decade = _era_decade(era_id)
    if not decade:
        return 0

    search_queries = [
        f"{decade} vintage clothing",
        f"{decade} vintage dress",
        f"{decade} vintage fashion",
    ]

    conn = get_connection()
    stored = 0
    now = datetime.now(timezone.utc).isoformat()

    for query in search_queries:
        if stored >= target:
            break

        listings = _scrape_etsy_playwright(query, limit=(target - stored) * 2)

        for item in listings:
            if stored >= target:
                break
            title = item.get("title", "").strip()
            if not title:
                continue
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO validation_items "
                    "(source, true_era_id, true_decade, title, tags, price, item_url, scraped_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("etsy", era_id, decade, title, "[]",
                     item.get("price"), item.get("url"), now),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    stored += 1
            except Exception:
                pass

        conn.commit()
        time.sleep(2)

    conn.close()
    logger.info(f"Collected {stored} Etsy samples for era '{era_id}' ({decade})")
    return stored


def collect_all_eras(target_per_era: int = SAMPLES_PER_ERA) -> dict:
    results = {}
    for era in _ERAS:
        era_id = era["id"]
        results[era_id] = collect_era_samples(era_id, target_per_era)
        time.sleep(3)
    return results


# ── Validation run ─────────────────────────────────────────────────────────────

def run_validation(limit: int = 100) -> dict:
    """Run classifier on pending validation items. Returns summary counts."""
    from app.vintage.classifier import classify_garment

    conn = get_connection()
    rows = conn.execute(
        """SELECT vi.id, vi.true_era_id, vi.true_decade, vi.title, vi.tags
           FROM validation_items vi
           LEFT JOIN validation_results vr ON vr.item_id = vi.id
           WHERE vr.id IS NULL
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()

    total_run = decade_correct = era_correct = 0
    now = datetime.now(timezone.utc).isoformat()

    for row in rows:
        item_id = row["id"]
        true_era_id = row["true_era_id"]
        true_decade = row["true_decade"]
        tags = json.loads(row["tags"] or "[]")

        notes = row["title"]
        if tags:
            notes += f"\nTags: {', '.join(tags)}"

        descriptors = {
            "fabrics": [], "prints": [], "silhouettes": [], "brands": [],
            "colors": [], "aesthetics": [], "key_garments": [],
            "hardware": [], "embellishments": [], "labels": [],
            "notes": notes,
        }

        try:
            result = classify_garment(descriptors, images=[])
        except Exception as e:
            logger.warning(f"Classifier failed for item {item_id}: {e}")
            continue

        predicted_id = (result.get("primary_era") or {}).get("id")
        predicted_conf = (result.get("primary_era") or {}).get("confidence")
        alt_ids = [a.get("id") for a in result.get("alternate_eras") or []]

        predicted_decade = _era_decade(predicted_id) if predicted_id else None
        is_decade_correct = 1 if predicted_decade == true_decade else 0
        is_era_correct = 1 if predicted_id == true_era_id else 0

        conn = get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO validation_results "
            "(item_id, predicted_era_id, predicted_confidence, alternate_era_ids, "
            "is_decade_correct, is_era_correct, raw_response, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, predicted_id, predicted_conf, json.dumps(alt_ids),
             is_decade_correct, is_era_correct, json.dumps(result), now),
        )
        conn.commit()
        conn.close()

        total_run += 1
        decade_correct += is_decade_correct
        era_correct += is_era_correct
        time.sleep(0.3)

    return {"total_run": total_run, "decade_correct": decade_correct, "era_correct": era_correct}


# ── Accuracy lookup ────────────────────────────────────────────────────────────

def get_era_accuracy(era_id: str) -> dict | None:
    """Return decade accuracy for a specific era if we have enough validation samples."""
    conn = get_connection()
    row = conn.execute(
        """SELECT COUNT(*) AS samples,
                  AVG(vr.is_decade_correct) AS decade_accuracy,
                  AVG(vr.is_era_correct) AS era_accuracy
           FROM validation_results vr
           JOIN validation_items vi ON vi.id = vr.item_id
           WHERE vi.true_era_id = ?""",
        (era_id,),
    ).fetchone()
    conn.close()

    samples = row["samples"] if row else 0
    if samples < _MIN_SAMPLES_FOR_ACCURACY:
        return None
    return {
        "samples": samples,
        "decade_accuracy": round(row["decade_accuracy"], 3) if row["decade_accuracy"] is not None else None,
        "era_accuracy": round(row["era_accuracy"], 3) if row["era_accuracy"] is not None else None,
    }


def get_validation_stats() -> dict:
    """Return overall + per-era accuracy stats."""
    conn = get_connection()

    total_row = conn.execute("SELECT COUNT(*) AS total FROM validation_items").fetchone()
    validated_row = conn.execute(
        "SELECT COUNT(*) AS validated, SUM(is_decade_correct) AS decade_correct, "
        "SUM(is_era_correct) AS era_correct, AVG(predicted_confidence) AS avg_confidence "
        "FROM validation_results"
    ).fetchone()
    era_rows = conn.execute(
        """SELECT vi.true_era_id, vi.true_decade,
                  COUNT(vr.id) AS validated,
                  SUM(vr.is_decade_correct) AS decade_correct,
                  SUM(vr.is_era_correct) AS era_correct,
                  AVG(vr.predicted_confidence) AS avg_confidence
           FROM validation_items vi
           JOIN validation_results vr ON vr.item_id = vi.id
           GROUP BY vi.true_era_id ORDER BY vi.true_era_id"""
    ).fetchall()
    conn.close()

    total = total_row["total"] if total_row else 0
    validated = validated_row["validated"] or 0 if validated_row else 0
    decade_correct = validated_row["decade_correct"] or 0 if validated_row else 0
    era_correct = validated_row["era_correct"] or 0 if validated_row else 0
    avg_conf = validated_row["avg_confidence"] if validated_row else None

    per_era = []
    for r in era_rows:
        v = r["validated"] or 0
        dc = r["decade_correct"] or 0
        ec = r["era_correct"] or 0
        era_label = (_ERA_BY_ID.get(r["true_era_id"]) or {}).get("label", r["true_era_id"])
        per_era.append({
            "era_id": r["true_era_id"],
            "era_label": era_label,
            "decade": r["true_decade"],
            "samples": v,
            "decade_accuracy": round(dc / v, 3) if v > 0 else None,
            "era_accuracy": round(ec / v, 3) if v > 0 else None,
            "avg_confidence": round(r["avg_confidence"], 3) if r["avg_confidence"] else None,
        })

    return {
        "total_collected": total,
        "total_validated": validated,
        "pending": total - validated,
        "overall": {
            "decade_accuracy": round(decade_correct / validated, 3) if validated > 0 else None,
            "era_accuracy": round(era_correct / validated, 3) if validated > 0 else None,
            "avg_confidence": round(avg_conf, 3) if avg_conf else None,
            "decade_correct": int(decade_correct),
            "era_correct": int(era_correct),
        },
        "per_era": per_era,
    }
