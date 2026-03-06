"""
Unit tests for each data-source scraper.

Every test mocks the external HTTP call / library and then asserts that:
  1. The scraper function returns True (success)
  2. The expected metrics are written to the temporary database

External dependencies mocked:
  - Google Trends  → pytrends.request.TrendReq
  - eBay           → requests.post (OAuth) + requests.get (Browse API)
  - Etsy           → requests.get
  - Poshmark       → requests.get
  - Reddit         → requests.get
  - News           → urllib.request.urlopen
"""

import io
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, PropertyMock

import pandas as pd
import pytest

from conftest import db_rows


# ── Google Trends ─────────────────────────────────────────────────────────────

class TestGoogleTrendsScraper:
    def _mock_pytrends(self, keyword="vintage denim", n_weeks=10):
        """Return a mock TrendReq that yields synthetic weekly data."""
        dates = pd.date_range(end=datetime.utcnow(), periods=n_weeks, freq="W")
        df = pd.DataFrame({keyword: [float(30 + i) for i in range(n_weeks)]}, index=dates)
        df.index.name = "date"

        mock_pt = MagicMock()
        mock_pt.return_value.interest_over_time.return_value = df
        mock_pt.return_value.interest_by_region.return_value = pd.DataFrame()
        return mock_pt

    def test_scrape_returns_true_on_success(self, tmp_db):
        mock_pt = self._mock_pytrends()
        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.google_trends.TrendReq", mock_pt):
            from app.scrapers.google_trends import scrape_google_trends
            result = scrape_google_trends("vintage denim", retries=1)
        assert result is True

    def test_scrape_stores_search_volume_rows(self, tmp_db):
        mock_pt = self._mock_pytrends(n_weeks=5)
        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.google_trends.TrendReq", mock_pt):
            from app.scrapers.google_trends import scrape_google_trends
            scrape_google_trends("vintage denim", retries=1)

        rows = db_rows(
            tmp_db,
            "SELECT * FROM trend_data WHERE keyword=? AND source='google_trends' AND metric='search_volume'",
            ("vintage denim",),
        )
        assert len(rows) >= 5

    def test_scrape_returns_true_on_empty_dataframe(self, tmp_db):
        """Empty Google Trends response is treated as success (no data written, not a failure)."""
        mock_pt = MagicMock()
        mock_pt.return_value.interest_over_time.return_value = pd.DataFrame()
        mock_pt.return_value.interest_by_region.return_value = pd.DataFrame()
        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.google_trends.TrendReq", mock_pt), \
             patch("time.sleep", return_value=None):
            from app.scrapers.google_trends import scrape_google_trends
            result = scrape_google_trends("nonexistent keyword xyz", retries=1)
        assert result is True

        rows = db_rows(
            tmp_db,
            "SELECT * FROM trend_data WHERE keyword=? AND source='google_trends'",
            ("nonexistent keyword xyz",),
        )
        assert len(rows) == 0

    def test_scrape_retries_on_failure(self, tmp_db):
        """Scraper should retry up to `retries` times when an exception occurs."""
        call_count = {"n": 0}

        def failing_build(*a, **kw):
            call_count["n"] += 1
            raise Exception("Simulated API failure")

        mock_pt = MagicMock()
        mock_pt.return_value.build_payload.side_effect = failing_build

        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.google_trends.TrendReq", mock_pt), \
             patch("time.sleep", return_value=None):
            from app.scrapers.google_trends import scrape_google_trends
            result = scrape_google_trends("retry test", retries=3)

        assert result is False
        assert call_count["n"] == 3


# ── eBay ──────────────────────────────────────────────────────────────────────

class TestEbayScraper:
    def _mock_requests(self, prices=None):
        prices = prices or [25.0, 35.0, 45.0, 55.0]
        items = [
            {"price": {"value": str(p), "currency": "USD"}, "title": f"Vintage item {i}"}
            for i, p in enumerate(prices)
        ]

        token_resp = MagicMock()
        token_resp.json.return_value = {"access_token": "mock-token", "expires_in": 7200}
        token_resp.raise_for_status = MagicMock()

        search_resp = MagicMock()
        search_resp.json.return_value = {"itemSummaries": items, "total": len(items)}
        search_resp.raise_for_status = MagicMock()
        search_resp.status_code = 200

        sold_resp = MagicMock()
        sold_resp.json.return_value = {"findCompletedItemsResponse": [{"searchResult": [{"item": []}]}]}
        sold_resp.raise_for_status = MagicMock()

        return token_resp, search_resp, sold_resp

    def test_scrape_returns_true_on_success(self, tmp_db):
        token_resp, search_resp, sold_resp = self._mock_requests()
        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.ebay.requests.post", return_value=token_resp), \
             patch("app.scrapers.ebay.requests.get", return_value=search_resp):
            from app.scrapers.ebay import scrape_ebay
            result = scrape_ebay("vintage denim")
        assert result is True

    def test_scrape_stores_avg_price(self, tmp_db):
        token_resp, search_resp, sold_resp = self._mock_requests([20.0, 40.0, 60.0])
        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.ebay.requests.post", return_value=token_resp), \
             patch("app.scrapers.ebay.requests.get", return_value=search_resp):
            from app.scrapers.ebay import scrape_ebay
            scrape_ebay("leather jacket")

        rows = db_rows(
            tmp_db,
            "SELECT * FROM trend_data WHERE keyword=? AND source='ebay' AND metric='avg_price'",
            ("leather jacket",),
        )
        assert len(rows) >= 1
        assert rows[0]["value"] == pytest.approx(40.0, abs=1.0)

    def test_scrape_stores_listing_count(self, tmp_db):
        token_resp, search_resp, _ = self._mock_requests([10.0, 20.0, 30.0])
        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.ebay.requests.post", return_value=token_resp), \
             patch("app.scrapers.ebay.requests.get", return_value=search_resp):
            from app.scrapers.ebay import scrape_ebay
            scrape_ebay("corduroy jacket")

        rows = db_rows(
            tmp_db,
            "SELECT * FROM trend_data WHERE keyword=? AND source='ebay' AND metric='sold_count'",
            ("corduroy jacket",),
        )
        assert len(rows) >= 1


# ── Etsy ──────────────────────────────────────────────────────────────────────

class TestEtsyScraper:
    def _mock_etsy_response(self, prices=None):
        prices = prices or [18.0, 32.0, 45.0]
        listings = [
            {
                "listing_id": i,
                "title": f"Handmade item {i}",
                "price": {"amount": int(p * 100), "divisor": 100, "currency_code": "USD"},
                "quantity": 1,
            }
            for i, p in enumerate(prices)
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": listings, "count": len(listings)}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_scrape_returns_true(self, tmp_db):
        mock_resp = self._mock_etsy_response()
        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.etsy.requests.get", return_value=mock_resp):
            from app.scrapers.etsy import scrape_etsy
            result = scrape_etsy("vintage dress")
        assert result is True

    def test_scrape_stores_avg_price(self, tmp_db):
        mock_resp = self._mock_etsy_response([10.0, 20.0, 30.0])
        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.etsy.requests.get", return_value=mock_resp):
            from app.scrapers.etsy import scrape_etsy
            scrape_etsy("floral blouse")

        rows = db_rows(
            tmp_db,
            "SELECT * FROM trend_data WHERE keyword=? AND source='etsy' AND metric='avg_price'",
            ("floral blouse",),
        )
        assert len(rows) >= 1
        assert rows[0]["value"] == pytest.approx(20.0, abs=2.0)


# ── Poshmark ──────────────────────────────────────────────────────────────────

class TestPoshmarkScraper:
    def _mock_poshmark_html(self, prices=None):
        prices = prices or [15.0, 25.0, 35.0]
        price_json = "".join(
            f'"price_amount": {{"val": "{p}", "currency_code": "USD"}},'
            for p in prices
        )
        html = f"<html><body>{price_json}</body></html>"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        return mock_resp

    def test_scrape_returns_true(self, tmp_db):
        mock_resp = self._mock_poshmark_html()
        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.poshmark.requests.get", return_value=mock_resp):
            from app.scrapers.poshmark import scrape_poshmark
            result = scrape_poshmark("silk blouse")
        assert result is True

    def test_scrape_stores_listing_count(self, tmp_db):
        mock_resp = self._mock_poshmark_html([20.0, 30.0, 40.0])
        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.poshmark.requests.get", return_value=mock_resp):
            from app.scrapers.poshmark import scrape_poshmark
            scrape_poshmark("blazer")

        rows = db_rows(
            tmp_db,
            "SELECT * FROM trend_data WHERE keyword=? AND source='poshmark' AND metric='listing_count'",
            ("blazer",),
        )
        assert len(rows) >= 1
        assert rows[0]["value"] == 3


# ── Reddit ────────────────────────────────────────────────────────────────────

class TestRedditScraper:
    def _mock_reddit_json(self, n_posts=5):
        posts = [
            {
                "data": {
                    "title": f"Great vintage find #{i}",
                    "score": 100 + i * 10,
                    "created_utc": (datetime.now(timezone.utc) - timedelta(days=i)).timestamp(),
                }
            }
            for i in range(n_posts)
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"children": posts}}
        return mock_resp

    def test_scrape_returns_true(self, tmp_db):
        mock_resp = self._mock_reddit_json()
        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.reddit.requests.get", return_value=mock_resp):
            from app.scrapers.reddit import scrape_reddit
            result = scrape_reddit("vintage clothing")
        assert result is True

    def test_scrape_stores_mention_count(self, tmp_db):
        mock_resp = self._mock_reddit_json(n_posts=8)
        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.reddit.requests.get", return_value=mock_resp):
            from app.scrapers.reddit import scrape_reddit
            scrape_reddit("thrift haul")

        rows = db_rows(
            tmp_db,
            "SELECT * FROM trend_data WHERE keyword=? AND source='reddit' AND metric='mention_count'",
            ("thrift haul",),
        )
        assert len(rows) >= 1
        # Total mentions = n_posts per subreddit × number of subreddits
        assert rows[0]["value"] > 0


# ── News ─────────────────────────────────────────────────────────────────────

class TestNewsScraper:
    def _mock_rss_feed(self, n_articles=4):
        """Build a minimal Atom/RSS XML string."""
        items = "\n".join(
            f"""<item>
                <title>Fashion trend: vintage style #{i}</title>
                <description>Article about vintage fashion trend number {i}</description>
                <pubDate>Thu, 01 Jan 2026 00:00:00 +0000</pubDate>
            </item>"""
            for i in range(n_articles)
        )
        xml_str = f"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Google News</title>{items}</channel></rss>"""
        return xml_str.encode("utf-8")

    def test_scrape_returns_true(self, tmp_db):
        mock_response = MagicMock()
        mock_response.read.return_value = self._mock_rss_feed()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.news.urllib.request.urlopen", return_value=mock_response):
            from app.scrapers.news import scrape_news
            result = scrape_news("vintage fashion")
        assert result is True

    def test_scrape_stores_news_mentions(self, tmp_db):
        mock_response = MagicMock()
        mock_response.read.return_value = self._mock_rss_feed(n_articles=3)
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("app.database.DB_PATH", tmp_db), \
             patch("app.scrapers.news.urllib.request.urlopen", return_value=mock_response):
            from app.scrapers.news import scrape_news
            scrape_news("retro style")

        rows = db_rows(
            tmp_db,
            "SELECT * FROM trend_data WHERE keyword=? AND source='news' AND metric='news_mentions'",
            ("retro style",),
        )
        assert len(rows) >= 1
        assert rows[0]["value"] >= 1
