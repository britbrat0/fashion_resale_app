import json
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.auth.service import get_current_user
from app.database import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vintage", tags=["vintage"])

# Load era data once at import time
_ERA_DATA_PATH = Path(__file__).parent / "era_data.json"
with _ERA_DATA_PATH.open() as _f:
    _ERAS: list[dict] = json.load(_f)

_ERA_BY_ID: dict[str, dict] = {era["id"]: era for era in _ERAS}

# How long before era images are considered stale (hours)
_IMAGE_STALE_HOURS = 24


def _backfill_era_images() -> None:
    """On startup: scrape Pinterest for any era that has fewer than 6 cached images."""
    import time
    from app.scrapers.pinterest import scrape_pinterest_era
    for era in _ERAS:
        era_id = era["id"]
        if len(_query_era_images(era_id)) < 6:
            search_terms = era.get("image_search_terms", [era["label"] + " fashion vintage"])
            logger.info(f"Backfill: scraping Pinterest for era '{era_id}'")
            scrape_pinterest_era(era_id, search_terms)
            time.sleep(3)  # polite pause between eras


threading.Thread(target=_backfill_era_images, daemon=True).start()


def _era_images_stale(era_id: str) -> bool:
    """Return True if era images are missing or older than _IMAGE_STALE_HOURS."""
    keyword = f"vintage:{era_id}"
    threshold = (datetime.now(timezone.utc) - timedelta(hours=_IMAGE_STALE_HOURS)).isoformat()
    conn = get_connection()
    row = conn.execute(
        "SELECT scraped_at FROM trend_images WHERE keyword = ? "
        "ORDER BY scraped_at DESC LIMIT 1",
        (keyword,),
    ).fetchone()
    conn.close()
    if not row:
        return True
    return row["scraped_at"] < threshold


def _query_era_images(era_id: str) -> list[dict]:
    """Fetch up to 6 cached Pinterest images for this era (Wikimedia excluded)."""
    keyword = f"vintage:{era_id}"
    conn = get_connection()
    rows = conn.execute(
        "SELECT image_url, title, item_url, source FROM trend_images "
        "WHERE keyword = ? AND source != 'wikimedia' ORDER BY scraped_at DESC LIMIT 6",
        (keyword,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/eras")
def list_eras(user: str = Depends(get_current_user)):
    """Return summary list of all 24 eras (id, label, period, start_year, end_year)."""
    summary = [
        {
            "id": era["id"],
            "label": era["label"],
            "period": era["period"],
            "start_year": era["start_year"],
            "end_year": era["end_year"],
        }
        for era in _ERAS
    ]
    return {"eras": summary}


@router.get("/eras/{era_id}/images")
def era_images(era_id: str):
    """Return up to 6 Pinterest images for this era.

    On first visit: blocks while Pinterest scrapes (45 s timeout).
    On subsequent visits: returns cached images; refreshes in background if stale.
    """
    if era_id not in _ERA_BY_ID:
        raise HTTPException(status_code=404, detail=f"Era '{era_id}' not found")

    era = _ERA_BY_ID[era_id]
    search_terms = era.get("image_search_terms", [era["label"] + " fashion vintage"])

    images = _query_era_images(era_id)

    if len(images) < 4:
        # ── First visit: block on Pinterest scrape ────────────────────────────
        from app.scrapers.pinterest import scrape_pinterest_era
        t = threading.Thread(target=scrape_pinterest_era, args=(era_id, search_terms))
        t.start()
        t.join(timeout=45)
        images = _query_era_images(era_id)

    elif _era_images_stale(era_id):
        # ── Stale cache: return immediately, refresh Pinterest in background ──
        from app.scrapers.pinterest import scrape_pinterest_era
        threading.Thread(
            target=scrape_pinterest_era, args=(era_id, search_terms), daemon=True
        ).start()

    response = JSONResponse({"era_id": era_id, "images": images})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


def _clean_chip(val: str) -> str:
    """Strip trailing parenthetical context from a descriptor value.

    e.g. 'Spandex (disco)' -> 'Spandex'
         'Earth tones (hippie)' -> 'Earth tones'
         'Chanel (returning)' -> 'Chanel'
    """
    return re.sub(r'\s*\([^)]*\)\s*$', '', val).strip()


@router.get("/descriptor-options")
def descriptor_options(user: str = Depends(get_current_user)):
    """Return aggregated unique values across all eras for each descriptor category."""
    categories = ("fabrics", "prints", "silhouettes", "brands", "colors", "aesthetics", "key_garments")
    result = {cat: set() for cat in categories}
    for era in _ERAS:
        for cat in categories:
            for item in era.get(cat, []):
                result[cat].add(_clean_chip(item))
    return {cat: sorted(result[cat]) for cat in categories}


@router.post("/classify")
async def classify(
    user: str = Depends(get_current_user),
    fabrics: str = Form(default="[]"),
    prints: str = Form(default="[]"),
    silhouettes: str = Form(default="[]"),
    brands: str = Form(default="[]"),
    colors: str = Form(default="[]"),
    aesthetics: str = Form(default="[]"),
    key_garments: str = Form(default="[]"),
    hardware: str = Form(default="[]"),
    embellishments: str = Form(default="[]"),
    labels: str = Form(default="[]"),
    notes: str = Form(default=""),
    image_0: UploadFile | None = File(default=None),
    image_1: UploadFile | None = File(default=None),
    image_2: UploadFile | None = File(default=None),
    image_3: UploadFile | None = File(default=None),
    image_4: UploadFile | None = File(default=None),
    image_5: UploadFile | None = File(default=None),
    image_6: UploadFile | None = File(default=None),
    image_7: UploadFile | None = File(default=None),
    image_8: UploadFile | None = File(default=None),
    image_9: UploadFile | None = File(default=None),
):
    """Classify a garment by descriptors and/or images."""
    from app.vintage.classifier import classify_garment

    # Parse descriptor JSON arrays
    try:
        descriptors = {
            "fabrics": json.loads(fabrics),
            "prints": json.loads(prints),
            "silhouettes": json.loads(silhouettes),
            "brands": json.loads(brands),
            "colors": json.loads(colors),
            "aesthetics": json.loads(aesthetics),
            "key_garments": json.loads(key_garments),
            "hardware": json.loads(hardware),
            "embellishments": json.loads(embellishments),
            "labels": json.loads(labels),
            "notes": notes,
        }
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in descriptor field: {e}")

    # Collect uploaded images
    image_files = [image_0, image_1, image_2, image_3, image_4,
                   image_5, image_6, image_7, image_8, image_9]
    images: list[bytes] = []
    for f in image_files:
        if f is not None:
            images.append(await f.read())

    # Require at least one input
    has_descriptors = any(
        descriptors.get(k) for k in ("fabrics", "prints", "silhouettes", "brands",
                                      "colors", "aesthetics", "key_garments")
    ) or bool(notes.strip())
    if not has_descriptors and not images:
        raise HTTPException(status_code=400, detail="Provide at least one descriptor or image.")

    # Call classifier (retry once on JSON parse error)
    try:
        result = classify_garment(descriptors, images)
    except json.JSONDecodeError:
        try:
            result = classify_garment(descriptors, images)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=422, detail=f"Failed to parse Claude response: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {e}")

    # Attach era accuracy if validation data exists
    primary_id = result.get("primary_era", {}).get("id")
    if primary_id:
        from app.vintage.validation import get_era_accuracy
        acc = get_era_accuracy(primary_id)
        if acc:
            result["era_accuracy"] = acc

    return {"status": "ok", "result": result}


@router.post("/validation/collect-era")
def validation_collect_era(era_id: str, target: int = 5, user: str = Depends(get_current_user)):
    """Background: collect Etsy samples for one era then validate pending items."""
    if era_id not in _ERA_BY_ID:
        raise HTTPException(status_code=404, detail=f"Era '{era_id}' not found")

    def _task():
        from app.vintage.validation import collect_era_samples, run_validation
        collect_era_samples(era_id, target)
        run_validation(limit=50)

    threading.Thread(target=_task, daemon=True).start()
    return {"status": "started", "era_id": era_id}


@router.get("/etsy-listings")
def etsy_listings(q: str, user: str = Depends(get_current_user)):
    """Search Etsy for active vintage listings matching a keyword."""
    from app.vintage.validation import search_etsy_listings
    return {"query": q, "listings": search_etsy_listings(q, limit=6)}


@router.get("/eras/{era_id}/market")
def era_market(era_id: str, user: str = Depends(get_current_user)):
    """Return full market data for an era.

    Returns:
      price_stats:    {avg, min, max, count, source} or null
      by_platform:    {ebay: {avg, count}, etsy: …, poshmark: …, depop: …}
      lifecycle_stage: string or null (from trend_scores for era-related keywords)
      demand_score:   float or null
      garment_prices: {garment_name: avg_price} for key_garments with matching data
    """
    if era_id not in _ERA_BY_ID:
        raise HTTPException(status_code=404, detail=f"Era '{era_id}' not found")

    era = _ERA_BY_ID[era_id]
    conn = get_connection()

    # ── Source 1: trend_images prices for this era's vintage keyword ──────────
    era_keyword = f"vintage:{era_id}"
    img_row = conn.execute(
        "SELECT AVG(price) AS avg, MIN(price) AS min, MAX(price) AS max, COUNT(*) AS cnt "
        "FROM trend_images WHERE keyword = ? AND price IS NOT NULL AND price > 0",
        (era_keyword,),
    ).fetchone()

    price_stats = None
    if img_row and img_row["cnt"] > 0:
        price_stats = {
            "avg": round(img_row["avg"], 2),
            "min": round(img_row["min"], 2),
            "max": round(img_row["max"], 2),
            "count": img_row["cnt"],
            "source": "listings",
        }

    # ── Build search terms: decades + brand names + key garment words ────────
    start_year = era.get("start_year", 0)
    end_year = era.get("end_year", 0)
    decade_start = (start_year // 10) * 10
    decade_end = (end_year // 10) * 10

    search_terms: set[str] = set()

    # Decade strings (e.g. "1970s", "70s")
    for y in range(decade_start, decade_end + 1, 10):
        search_terms.add(f"{y}s")
        search_terms.add(f"{str(y)[2:4]}s")

    # Brand names: first meaningful word of each brand (4+ chars)
    for brand in era.get("brands", []):
        clean = re.sub(r'\(.*?\)', '', brand).strip()
        first_word = clean.split()[0].lower().strip("',.")
        if len(first_word) >= 4:
            search_terms.add(first_word)

    # Key garment + fabric words (5+ chars, skipping short prepositions/articles)
    _SKIP = {"with", "and", "the", "for", "of", "a", "an"}
    for item in era.get("key_garments", []) + era.get("fabrics", []):
        for word in item.lower().split():
            word_clean = word.strip("'s,.-/()")
            if len(word_clean) >= 5 and word_clean not in _SKIP:
                search_terms.add(word_clean)

    decades = search_terms  # reuse variable name for downstream compatibility

    by_platform: dict = {}
    lifecycle_stage: str | None = None
    demand_score: float | None = None

    if search_terms:
        decade_list = sorted(search_terms)
        like_clauses = " OR ".join(["LOWER(keyword) LIKE ?" for _ in decade_list])
        params = [f"%{t.lower()}%" for t in decade_list]

        # Platform breakdown
        platform_rows = conn.execute(
            f"SELECT source, AVG(value) AS avg_price, COUNT(*) AS cnt "
            f"FROM trend_data "
            f"WHERE ({like_clauses}) AND metric = 'avg_price' AND value > 0 "
            f"GROUP BY source",
            params,
        ).fetchall()
        for row in platform_rows:
            by_platform[row["source"]] = {"avg": round(row["avg_price"], 2), "count": row["cnt"]}

        # Fallback price_stats from trend_data when no trend_images data
        if not price_stats:
            td_row = conn.execute(
                f"SELECT AVG(value) AS avg, MIN(value) AS min, MAX(value) AS max, COUNT(*) AS cnt "
                f"FROM trend_data "
                f"WHERE ({like_clauses}) AND metric = 'avg_price' AND value > 0",
                params,
            ).fetchone()
            if td_row and td_row["cnt"] > 0:
                price_stats = {
                    "avg": round(td_row["avg"], 2),
                    "min": round(td_row["min"], 2),
                    "max": round(td_row["max"], 2),
                    "count": td_row["cnt"],
                    "source": "tracked_keywords",
                }

        # Lifecycle stage — most recent, highest-scoring tracked keyword for this era
        ts_row = conn.execute(
            f"SELECT lifecycle_stage, composite_score "
            f"FROM trend_scores "
            f"WHERE ({like_clauses}) "
            f"ORDER BY computed_at DESC, composite_score DESC LIMIT 1",
            params,
        ).fetchone()
        if ts_row and ts_row["lifecycle_stage"]:
            lifecycle_stage = ts_row["lifecycle_stage"]
            demand_score = round(ts_row["composite_score"], 1) if ts_row["composite_score"] is not None else None

    # ── Per-garment prices from trend_data ────────────────────────────────────
    garment_prices: dict[str, float] = {}
    for garment in era.get("key_garments", []):
        g_lower = garment.lower()
        row = conn.execute(
            "SELECT AVG(value) AS avg_price FROM trend_data "
            "WHERE LOWER(keyword) LIKE ? AND metric = 'avg_price' AND value > 0",
            (f"%{g_lower}%",),
        ).fetchone()
        if row and row["avg_price"] is not None:
            garment_prices[garment] = round(row["avg_price"], 2)

    conn.close()
    return {
        "era_id": era_id,
        "price_stats": price_stats,
        "by_platform": by_platform,
        "lifecycle_stage": lifecycle_stage,
        "demand_score": demand_score,
        "garment_prices": garment_prices,
    }


@router.get("/etsy-listings")
def etsy_listings(q: str, user: str = Depends(get_current_user)):
    """Search Etsy for active vintage listings matching a keyword."""
    from app.vintage.validation import search_etsy_listings
    return {"query": q, "listings": search_etsy_listings(q, limit=6)}


@router.get("/eras/{era_id}")
def era_detail(era_id: str, user: str = Depends(get_current_user)):
    """Return full era details (all fields except image_search_terms)."""
    if era_id not in _ERA_BY_ID:
        raise HTTPException(status_code=404, detail=f"Era '{era_id}' not found")

    era = dict(_ERA_BY_ID[era_id])
    era.pop("image_search_terms", None)
    # Strip trailing parenthetical context from all list fields
    for field in ("fabrics", "prints", "silhouettes", "brands", "colors",
                  "aesthetics", "key_garments"):
        if isinstance(era.get(field), list):
            era[field] = [_clean_chip(v) for v in era[field]]
    return era
