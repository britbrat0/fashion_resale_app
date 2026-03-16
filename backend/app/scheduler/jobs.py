import logging
import time
import random
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.scrapers.google_trends import scrape_google_trends
from app.scrapers.ebay import scrape_ebay
from app.scrapers.reddit import scrape_reddit
from app.scrapers.tiktok import scrape_tiktok
from app.scrapers.depop import scrape_depop
from app.scrapers.etsy import scrape_etsy
from app.scrapers.poshmark import scrape_poshmark
from app.scrapers.news import scrape_news
from app.scrapers.discovery import get_active_keywords, run_discovery, refine_scale_classifications
from app.database import get_connection
from app.trends.service import compute_and_store_scores

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def scrape_all_sources():
    """Scrape marketplace and social sources for all active keywords.
    Google Trends is handled by the dedicated scrape_google_trends_all job."""
    keywords = get_active_keywords()
    logger.info(f"Starting scheduled scrape for {len(keywords)} keywords")

    for keyword in keywords:
        logger.info(f"Scraping keyword: '{keyword}'")
        scrape_ebay(keyword)
        scrape_reddit(keyword)
        try:
            scrape_tiktok(keyword)
        except Exception as e:
            logger.warning(f"TikTok scrape skipped for '{keyword}': {e}")
        scrape_depop(keyword)
        scrape_etsy(keyword)
        scrape_poshmark(keyword)
        try:
            scrape_news(keyword)
        except Exception as e:
            logger.warning(f"News scrape skipped for '{keyword}': {e}")
        time.sleep(random.uniform(5, 10))

    logger.info("Scheduled scrape complete")


def scrape_google_trends_all():
    """Dedicated Google Trends job. Scrapes all active keywords that lack recent data,
    with generous delays to stay within Google's rate limits.
    Google Trends returns weekly data, so keywords are only re-scraped if their most recent
    data point is older than 7 days."""
    threshold = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT k.keyword FROM keywords k
        WHERE k.status = 'active'
          AND NOT EXISTS (
              SELECT 1 FROM trend_data t
              WHERE t.keyword = k.keyword
                AND t.source = 'google_trends'
                AND t.metric = 'search_volume'
                AND t.recorded_at >= ?
          )
        ORDER BY k.keyword
        """,
        (threshold,),
    ).fetchall()
    conn.close()

    keywords_to_scrape = [r["keyword"] for r in rows]
    if not keywords_to_scrape:
        logger.info("Google Trends: all keywords have recent data — nothing to scrape")
        return

    logger.info(f"Google Trends: scraping {len(keywords_to_scrape)} keyword(s) needing updates")
    for i, keyword in enumerate(keywords_to_scrape):
        success = scrape_google_trends(keyword)
        if success:
            try:
                compute_and_store_scores(keyword)
            except Exception as e:
                logger.error(f"Google Trends: failed to score '{keyword}': {e}")
        # 40-60s between keywords — well within Google's rate limit threshold
        if i < len(keywords_to_scrape) - 1:
            time.sleep(random.uniform(40, 60))

    logger.info(f"Google Trends: completed scrape for {len(keywords_to_scrape)} keyword(s)")


def compute_all_scores():
    """Recompute composite scores for all active keywords."""
    keywords = get_active_keywords()
    logger.info(f"Computing scores for {len(keywords)} keywords")

    for keyword in keywords:
        try:
            compute_and_store_scores(keyword)
        except Exception as e:
            logger.error(f"Failed to compute scores for '{keyword}': {e}")

    logger.info("Score computation complete")


def catchup_google_trends():
    """Re-scrape Google Trends for any active keyword that has no search_volume data
    from the last 10 days. Runs after the main scrape to recover from rate-limit failures.
    Note: Google Trends returns weekly data, so the most recent point is up to 7 days old."""
    threshold = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT k.keyword FROM keywords k
        WHERE k.status = 'active'
          AND NOT EXISTS (
              SELECT 1 FROM trend_data t
              WHERE t.keyword = k.keyword
                AND t.source = 'google_trends'
                AND t.metric = 'search_volume'
                AND t.recorded_at >= ?
          )
        """,
        (threshold,),
    ).fetchall()
    conn.close()

    missing = [r["keyword"] for r in rows]
    if not missing:
        logger.info("Catch-up: all keywords have recent Google Trends data")
        return

    logger.info(f"Catch-up: re-scraping Google Trends for {len(missing)} keyword(s): {missing}")
    for i, keyword in enumerate(missing):
        success = scrape_google_trends(keyword)
        if success:
            try:
                compute_and_store_scores(keyword)
            except Exception as e:
                logger.error(f"Catch-up: failed to compute scores for '{keyword}': {e}")
        if i < len(missing) - 1:
            time.sleep(random.uniform(40, 60))  # match dedicated GT job pacing

    logger.info("Catch-up complete")


def scrape_and_score():
    """Combined job: scrape all sources then compute scores."""
    scrape_all_sources()
    compute_all_scores()


def discover_keywords():
    """Run keyword auto-discovery."""
    run_discovery()


def refine_keyword_scales():
    """Data-driven weekly review of macro/micro classifications."""
    refine_scale_classifications()


def expire_stale_keywords():
    """Deactivate user_search keywords not searched in the last 30 days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    conn = get_connection()
    result = conn.execute(
        "UPDATE keywords SET status = 'inactive' WHERE source = 'user_search' AND status = 'active' AND (last_searched_at IS NULL OR last_searched_at < ?)",
        (cutoff,),
    )
    expired = result.rowcount
    conn.commit()
    conn.close()
    if expired:
        logger.info(f"Auto-expired {expired} stale user-searched keyword(s)")


def scrape_single_keyword(keyword: str):
    """On-demand scrape for a single keyword across all sources."""
    logger.info(f"On-demand scrape for '{keyword}'")
    scrape_google_trends(keyword)
    scrape_ebay(keyword)
    scrape_reddit(keyword)
    try:
        scrape_tiktok(keyword)
    except Exception as e:
        logger.warning(f"TikTok scrape skipped for '{keyword}': {e}")
    scrape_depop(keyword)
    scrape_etsy(keyword)
    scrape_poshmark(keyword)
    try:
        scrape_news(keyword)
    except Exception as e:
        logger.warning(f"News scrape skipped for '{keyword}': {e}")
    compute_and_store_scores(keyword)
    logger.info(f"On-demand scrape and scoring complete for '{keyword}'")


def start_scheduler():
    """Initialize and start the background scheduler."""
    now = datetime.now(timezone.utc)

    # Scrape + score (marketplace + social) every 6 hours — run immediately on startup
    scheduler.add_job(scrape_and_score, "interval", hours=6, id="scrape_and_score", replace_existing=True,
                      next_run_time=now)

    # Dedicated Google Trends job — runs every 8 hours, starts 5 min after startup
    # Uses 40-60s delays between keywords to stay within rate limits
    scheduler.add_job(scrape_google_trends_all, "interval", hours=8, id="scrape_google_trends_all", replace_existing=True,
                      next_run_time=now + timedelta(minutes=5))

    # Catch-up Google Trends — retries any still-missing keywords 3 hours after startup, then every 8h
    scheduler.add_job(catchup_google_trends, "interval", hours=8, id="catchup_google_trends", replace_existing=True,
                      next_run_time=now + timedelta(hours=3))

    # Auto-discover new keywords every 24 hours
    scheduler.add_job(discover_keywords, "interval", hours=24, id="discover_keywords", replace_existing=True)

    # Expire stale user-searched keywords daily
    scheduler.add_job(expire_stale_keywords, "interval", hours=24, id="expire_stale_keywords", replace_existing=True)

    # Refine macro/micro classifications weekly using statistical signals
    scheduler.add_job(refine_keyword_scales, "interval", days=7, id="refine_keyword_scales", replace_existing=True)

    scheduler.start()
    logger.info("Scheduler started: scrape_and_score(marketplace+social) every 6h, scrape_google_trends_all every 8h (+5min), catchup_google_trends every 8h (+3h), discover_keywords every 24h, expire_stale_keywords every 24h, refine_keyword_scales every 7d")


def stop_scheduler():
    """Shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
