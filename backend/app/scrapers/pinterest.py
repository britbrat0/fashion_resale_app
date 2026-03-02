import io
import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests as _requests

from app.database import get_connection


def _analyze_image(url: str):
    """Download an image and return (phash_str_or_None, is_text_heavy).

    Text detection uses two signals (either triggers a rejection):
      1. OCR (pytesseract): reads actual text regardless of color/background.
         - >= 8 words found  →  flagged (large text block)
         - >= 4 words AND title matches article patterns  →  flagged
      2. Near-white pixel ratio fallback: catches white text-box cards when OCR
         is unavailable.

    Returns (None, False) on failure so images are never wrongly rejected.
    """
    try:
        import imagehash
        from PIL import Image
        r = _requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        phash_str = str(imagehash.phash(img))

        is_text_heavy = False

        # Signal 1: OCR — works on any text color / background
        try:
            import pytesseract
            # 300x300 is plenty for OCR and keeps latency low (~0.3s per image)
            ocr_img = img.resize((300, 300))
            ocr_text = pytesseract.image_to_string(
                ocr_img, config="--psm 11 --oem 3"
            )
            words = [w for w in ocr_text.split() if len(w) > 2]
            if len(words) >= 8:
                # Large text block — definitely an article/guide image
                is_text_heavy = True
                logger.debug(f"OCR flagged image ({len(words)} words): {url[:60]}")
            elif len(words) >= 4 and _is_article_pin(ocr_text):
                # Fewer words but matches article-title pattern (e.g. "A Guide to Mastering")
                is_text_heavy = True
                logger.debug(f"OCR+pattern flagged image: {url[:60]}")
        except Exception:
            # pytesseract unavailable — fall through to pixel-ratio fallback
            pass

        # Signal 2: Near-white pixel ratio (fast, no OCR required)
        # Catches white-box text cards regardless of OCR availability
        if not is_text_heavy:
            small = img.resize((64, 64))
            pixels = list(small.getdata())
            near_white = sum(1 for rv, g, b in pixels if rv > 235 and g > 235 and b > 235)
            if (near_white / len(pixels)) > 0.18:
                is_text_heavy = True

        return phash_str, is_text_heavy
    except Exception:
        return None, False

logger = logging.getLogger(__name__)

# Patterns that indicate a Pinterest "idea pin" / blog post collage rather than a clean photo
_ARTICLE_PATTERNS = re.compile(
    r'\b\d+\s'                          # starts with a number ("8 Luxury...", "10 Ways...")
    r'|how\s+to\b'                      # "how to style"
    r'|\bways?\s+to\b'                  # "ways to wear"
    r'|\bwhat\s+to\s+wear\b'            # "what to wear"
    r'|\btips?\b'                       # "tips for"
    r'|\bguide\b'                       # "ultimate guide"
    r'|\bmastering\b'                   # "mastering the art of"
    r'|\btutorial\b'                    # "tutorial"
    r'|\byou\s+need\b'                  # "everything you need"
    r'|\bmust.?have\b'                  # "must-have" or "must have"
    r'|\bbrands?\b'                     # "best brands"
    r'|\.com\b'                         # contains a domain ("gooseberryintimates.com")
    r'|\binspo\s+board\b'               # "inspo board"
    r'|\bideas\b'                       # "outfit ideas", "style ideas"
    r'|\bessentials\b'                  # "wardrobe essentials"
    r'|\bwardrobe\b'                    # "build a wardrobe"
    r'|\bbuild\s+a\b'                   # "build a..."
    r'|\blook\s+book\b'                 # "look book"
    r'|\blookbook\b'                    # "lookbook"
    r'|\bcheat\s+sheet\b'               # "cheat sheet"
    r'|\binspiration\s+board\b'         # "inspiration board"
    r'|\baction\s+item\b'               # Pinterest UI artifact
    r'|\bpreview\s+image\b'             # "Preview Image" UI artifacts
    r'|\bcheck\s+out\b'                 # "Check out these..."
    r'|\baesthetic\s+refers\b'          # "aesthetic refers to..." (description text)
    r'|\bdress\s+like\b'                # "dress like a mob wife"
    r'|\bstyle\s+guide\b'               # "style guide"
    r'|\ba\s+guide\s+to\b'              # "a guide to..."
    r'|\bshop\s+the\s+look\b'           # "shop the look"
    r'|\bhere.?s\b'                     # "here's 5 ways..."
    r'|\bunder\s+\$'                    # "under $50"
    r'|\bwhere\s+to\s+(buy|find|shop)\b', # "where to buy"
    re.IGNORECASE,
)


def _is_article_pin(title: str) -> bool:
    """Return True if the pin title looks like a blog/listicle article rather than a photo."""
    if not title:
        return False
    return bool(_ARTICLE_PATTERNS.search(title))


def scrape_pinterest_images(keyword: str) -> list:
    """Scrape Pinterest search for fashion images using Playwright.
    Stores results in trend_images and returns the list."""
    images = []
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()

            # Block fonts, media, and tracking to speed up load
            page.route(
                "**/*.{woff,woff2,ttf,otf,mp4,webm,ogg,mp3}",
                lambda route: route.abort(),
            )

            url = f"https://www.pinterest.com/search/pins/?q={quote_plus(keyword + ' fashion')}&rs=typed"
            try:
                page.goto(url, timeout=15000, wait_until="domcontentloaded")
            except Exception:
                browser.close()
                return []

            # Bail out if redirected to login
            if "login" in page.url or "signup" in page.url:
                logger.warning(f"Pinterest redirected to login for '{keyword}'")
                browser.close()
                return []

            # Wait for pin images from Pinterest CDN
            try:
                page.wait_for_selector("img[src*='i.pinimg.com']", timeout=10000)
            except Exception:
                browser.close()
                return []

            # Scroll once to load more pins
            page.evaluate("window.scrollBy(0, 600)")
            page.wait_for_timeout(1500)

            img_elements = page.query_selector_all("img[src*='i.pinimg.com']")

            seen_urls = set()
            candidates = []
            for img in img_elements:
                src = img.get_attribute("src") or ""
                if not src or src in seen_urls:
                    continue

                # Only accept actual pin images — must have a large-enough dimension in the URL
                # e.g. /236x/, /474x/, /564x/, /736x/  — skip 60x60, 75x75 avatars
                size_match = re.search(r'/(\d+)x/', src)
                if not size_match or int(size_match.group(1)) < 200:
                    continue

                # Upgrade to larger size for better quality
                for small, large in [("/236x/", "/564x/"), ("/474x/", "/564x/")]:
                    src = src.replace(small, large)

                alt = img.get_attribute("alt") or ""

                # Skip images with no alt text — real fashion photos always have descriptions
                if not alt.strip():
                    continue

                # Skip article/listicle collage pins
                if _is_article_pin(alt):
                    continue

                # Get the closest anchor link for the pin
                item_url = img.evaluate(
                    "el => el.closest('a') ? el.closest('a').href : null"
                )

                seen_urls.add(src)
                candidates.append({
                    "keyword": keyword,
                    "source": "pinterest",
                    "image_url": src,
                    "title": alt[:200] if alt else None,
                    "price": None,
                    "item_url": item_url,
                })

                if len(candidates) >= 8:
                    break

            images = candidates[:6]

            browser.close()

    except Exception as e:
        logger.error(f"Pinterest image scrape failed for '{keyword}': {e}")
        return []

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()

    # Clean up any existing text-heavy images for this keyword (title-based)
    existing = conn.execute(
        "SELECT id, title FROM trend_images WHERE keyword = ? AND source = 'pinterest'",
        (keyword,),
    ).fetchall()
    bad_ids = [r["id"] for r in existing if _is_article_pin(r["title"] or "")]
    if bad_ids:
        conn.execute(
            f"DELETE FROM trend_images WHERE id IN ({','.join('?' * len(bad_ids))})",
            bad_ids,
        )
        conn.commit()
        logger.info(f"Pinterest: cleaned up {len(bad_ids)} text-heavy image(s) for '{keyword}'")

    stored = 0
    for img in images:
        phash_val, is_text_heavy = _analyze_image(img["image_url"])
        if is_text_heavy:
            logger.info(f"Pinterest: skipping text-heavy image for '{keyword}'")
            continue
        conn.execute(
            "INSERT OR IGNORE INTO trend_images "
            "(keyword, source, image_url, title, price, item_url, scraped_at, phash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (img["keyword"], img["source"], img["image_url"],
             img["title"], img["price"], img["item_url"], now, phash_val),
        )
        stored += 1

    # Prune to 8 most recent per keyword
    conn.execute(
        """DELETE FROM trend_images WHERE keyword = ? AND id NOT IN (
            SELECT id FROM trend_images WHERE keyword = ?
            ORDER BY scraped_at DESC LIMIT 8
        )""",
        (keyword, keyword),
    )
    conn.commit()
    conn.close()
    if stored:
        logger.info(f"Pinterest: stored {stored} images for '{keyword}'")

    return images


def scrape_pinterest_era(era_id: str, search_terms: list) -> bool:
    """Scrape Pinterest for a vintage era using multiple search terms.

    Two-pass image selection:
      Pass 1 (diversity): take up to ceil(TARGET / terms) from each search term,
                          ensuring every aesthetic gets representation.
      Pass 2 (fill):      use leftover images from any term to reach TARGET=6.

    Uses a single shared browser instance across all terms for speed.
    Stores images with keyword='vintage:{era_id}' in trend_images.
    Returns True if any images were stored.
    """
    import math
    keyword = f"vintage:{era_id}"
    TARGET = 6
    num_terms = max(len(search_terms), 1)
    per_term_cap = math.ceil(TARGET / num_terms)

    # Scrape ALL terms first, storing candidates per term.
    # We collect more than per_term_cap per term so pass 2 has a reserve.
    term_batches: list[list[dict]] = []

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for term in search_terms:
                logger.info(f"Pinterest era scrape: trying '{term}' for era '{era_id}'")
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 900},
                )
                page = context.new_page()
                page.route(
                    "**/*.{woff,woff2,ttf,otf,mp4,webm,ogg,mp3}",
                    lambda route: route.abort(),
                )

                url = f"https://www.pinterest.com/search/pins/?q={quote_plus(term)}&rs=typed"
                try:
                    page.goto(url, timeout=15000, wait_until="domcontentloaded")
                except Exception:
                    context.close()
                    term_batches.append([])
                    continue

                if "login" in page.url or "signup" in page.url:
                    logger.warning(f"Pinterest redirected to login for era term '{term}'")
                    context.close()
                    term_batches.append([])
                    continue

                try:
                    page.wait_for_selector("img[src*='i.pinimg.com']", timeout=10000)
                except Exception:
                    context.close()
                    term_batches.append([])
                    continue

                # Two scrolls to load more pins before collecting
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(1200)
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(800)

                img_elements = page.query_selector_all("img[src*='i.pinimg.com']")
                seen_urls: set[str] = set()
                images: list[dict] = []
                for img in img_elements:
                    src = img.get_attribute("src") or ""
                    if not src or src in seen_urls:
                        continue
                    size_match = re.search(r'/(\d+)x/', src)
                    if not size_match or int(size_match.group(1)) < 200:
                        continue
                    for small, large in [("/236x/", "/564x/"), ("/474x/", "/564x/")]:
                        src = src.replace(small, large)
                    alt = img.get_attribute("alt") or ""
                    if not alt.strip():
                        continue
                    if _is_article_pin(alt):
                        continue
                    item_url = img.evaluate(
                        "el => el.closest('a') ? el.closest('a').href : null"
                    )
                    seen_urls.add(src)
                    images.append({
                        "keyword": keyword,
                        "source": "pinterest",
                        "image_url": src,
                        "title": alt[:200],
                        "price": None,
                        "item_url": item_url,
                    })
                    # Collect 2× target so text-heavy filter has plenty to reject from
                    if len(images) >= TARGET * 2:
                        break

                context.close()
                term_batches.append(images)

            browser.close()

    except Exception as e:
        logger.error(f"Pinterest era scrape failed for era '{era_id}': {e}")

    # ── Pass 1: diversity — take up to per_term_cap from each term ──────────
    collected: list[dict] = []
    reserve: list[dict] = []
    seen: set[str] = set()

    for images in term_batches:
        taken = 0
        for img in images:
            url = img["image_url"]
            if url in seen:
                continue
            if taken < per_term_cap:
                collected.append(img)
                seen.add(url)
                taken += 1
            else:
                reserve.append(img)

    # ── Pass 2: fill to TARGET using leftover images from any term ──────────
    for img in reserve:
        if len(collected) >= TARGET:
            break
        url = img["image_url"]
        if url not in seen:
            collected.append(img)
            seen.add(url)

    if not collected:
        logger.warning(f"Pinterest era scrape: no images found for era '{era_id}'")
        return False

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()

    # Clean up stale text-heavy images for this era keyword
    existing = conn.execute(
        "SELECT id, title FROM trend_images WHERE keyword = ? AND source = 'pinterest'",
        (keyword,),
    ).fetchall()
    bad_ids = [r["id"] for r in existing if _is_article_pin(r["title"] or "")]
    if bad_ids:
        conn.execute(
            f"DELETE FROM trend_images WHERE id IN ({','.join('?' * len(bad_ids))})",
            bad_ids,
        )
        conn.commit()

    stored = 0
    for img in collected:
        phash_val, is_text_heavy = _analyze_image(img["image_url"])
        if is_text_heavy:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO trend_images "
            "(keyword, source, image_url, title, price, item_url, scraped_at, phash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (img["keyword"], img["source"], img["image_url"],
             img["title"], img["price"], img["item_url"], now, phash_val),
        )
        stored += 1

    # Prune to 8 most recent for this era keyword
    conn.execute(
        """DELETE FROM trend_images WHERE keyword = ? AND id NOT IN (
            SELECT id FROM trend_images WHERE keyword = ?
            ORDER BY scraped_at DESC LIMIT 8
        )""",
        (keyword, keyword),
    )
    conn.commit()
    conn.close()

    if stored:
        logger.info(f"Pinterest era scrape: stored {stored} images for era '{era_id}'")
    return stored > 0
