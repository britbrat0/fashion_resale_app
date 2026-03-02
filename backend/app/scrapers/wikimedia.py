import logging
import re
from datetime import datetime, timezone

import requests

from app.database import get_connection

logger = logging.getLogger(__name__)

_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
_HEADERS = {"User-Agent": "FashionTrendForecaster/1.0 (educational project)"}

# Non-photo file extensions to skip
_SKIP_EXTS = (".svg", ".tif", ".tiff", ".pdf", ".ogv", ".ogg", ".webm", ".gif", ".png")

# Minimum image dimensions
_MIN_DIM = 400


def _search_files(term: str, limit: int = 12) -> list[str]:
    """Return a list of File: titles matching the search term on Commons."""
    try:
        r = requests.get(
            _COMMONS_API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": term,
                "srnamespace": "6",
                "srlimit": str(limit),
                "format": "json",
            },
            headers=_HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        return [x["title"] for x in r.json().get("query", {}).get("search", [])]
    except Exception as e:
        logger.warning(f"Wikimedia search failed for '{term}': {e}")
        return []


def _get_image_info(titles: list[str]) -> list[dict]:
    """Return image info dicts for a list of File: titles."""
    if not titles:
        return []
    try:
        r = requests.get(
            _COMMONS_API,
            params={
                "action": "query",
                "titles": "|".join(titles[:20]),
                "prop": "imageinfo",
                "iiprop": "url|size|extmetadata",
                "iiurlwidth": "800",   # request an 800px-wide thumbnail
                "format": "json",
            },
            headers=_HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        return list(r.json().get("query", {}).get("pages", {}).values())
    except Exception as e:
        logger.warning(f"Wikimedia imageinfo failed: {e}")
        return []


def _era_search_terms(era_id: str, era_label: str, era_period: str) -> list[str]:
    """Generate Wikimedia Commons search terms from era metadata."""
    # Strip parenthesized date from label: "Edwardian (1900s)" → "Edwardian"
    name = re.sub(r"\s*\([^)]+\)", "", era_label).strip()
    # Derive decade string: "1900–1909" → "1900s"
    start_str = re.split(r"[–\-]", era_period)[0].strip()
    try:
        decade = f"{str(int(start_str))[:3]}0s"
    except ValueError:
        decade = start_str
    return [
        f"{name} fashion",
        f"{decade} fashion photograph women",
    ]


def scrape_wikimedia_era(era_id: str, era_label: str, era_period: str, target: int = 6) -> int:
    """Fetch up to `target` images from Wikimedia Commons for a vintage era.

    Stores results in trend_images with source='wikimedia'.
    Returns the number of images stored.
    """
    keyword = f"vintage:{era_id}"
    search_terms = _era_search_terms(era_id, era_label, era_period)

    candidates: list[dict] = []
    seen_urls: set[str] = set()

    for term in search_terms:
        if len(candidates) >= target:
            break
        logger.info(f"Wikimedia era scrape: trying '{term}' for era '{era_id}'")

        titles = _search_files(term, limit=12)
        pages = _get_image_info(titles)

        for page in pages:
            if len(candidates) >= target:
                break

            info = (page.get("imageinfo") or [{}])[0]
            # Prefer the resized thumbnail URL; fall back to full resolution
            url = info.get("thumburl") or info.get("url", "")
            if not url or url in seen_urls:
                continue

            # Skip non-photo formats
            if any(url.lower().endswith(ext) for ext in _SKIP_EXTS):
                continue

            # Minimum size check (use original dimensions)
            if info.get("width", 0) < _MIN_DIM or info.get("height", 0) < _MIN_DIM:
                continue

            # Build a human-readable description from extmetadata
            ext = info.get("extmetadata", {})
            desc = ext.get("ImageDescription", {}).get("value", "")
            desc = re.sub(r"<[^>]+>", "", desc).strip()[:200]
            title_str = page.get("title", "").replace("File:", "")
            alt = desc or title_str[:200]

            item_url = info.get("descriptionurl", "")

            seen_urls.add(url)
            candidates.append({
                "keyword": keyword,
                "source": "wikimedia",
                "image_url": url,
                "title": alt,
                "price": None,
                "item_url": item_url,
            })

    if not candidates:
        logger.info(f"Wikimedia era scrape: no images found for era '{era_id}'")
        return 0

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    stored = 0
    for img in candidates:
        conn.execute(
            "INSERT OR IGNORE INTO trend_images "
            "(keyword, source, image_url, title, price, item_url, scraped_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                img["keyword"], img["source"], img["image_url"],
                img["title"], img["price"], img["item_url"], now,
            ),
        )
        stored += 1

    conn.commit()
    conn.close()

    if stored:
        logger.info(f"Wikimedia era scrape: stored {stored} images for era '{era_id}'")
    return stored
