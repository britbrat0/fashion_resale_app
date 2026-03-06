"""
Tests for the Trends API endpoints:
  GET  /api/trends/top
  GET  /api/trends/search
  GET  /api/trends/ranking-forecast
  GET  /api/trends/keywords/list
  POST /api/trends/keywords/{keyword}/track
  DELETE /api/trends/keywords/{keyword}
  GET  /api/trends/{keyword}/details
  GET  /api/trends/{keyword}/seasonal
  GET  /api/trends/{keyword}/images
  GET  /api/trends/keywords/{keyword}/sourcing  (mocked Claude)

The `client` fixture from conftest.py already overrides the auth dependency,
so every request is treated as coming from 'testuser@example.com'.
"""

import pytest
from unittest.mock import patch, MagicMock


# ── /api/trends/top ───────────────────────────────────────────────────────────

class TestTopTrends:
    def test_returns_200_with_trends_list(self, client):
        resp = client.get("/api/trends/top?period=7")
        assert resp.status_code == 200
        data = resp.json()
        assert "trends" in data
        assert isinstance(data["trends"], list)

    def test_period_param_accepted(self, client):
        for period in [7, 14, 30, 60, 90]:
            resp = client.get(f"/api/trends/top?period={period}")
            assert resp.status_code == 200

    def test_response_contains_period_days(self, client):
        resp = client.get("/api/trends/top?period=14")
        assert resp.json()["period_days"] == 14


# ── /api/trends/keywords ─────────────────────────────────────────────────────

class TestKeywordManagement:
    def _track(self, client, keyword):
        with patch("app.scheduler.jobs.scrape_single_keyword"):
            return client.post(f"/api/trends/keywords/{keyword}/track")

    def test_track_keyword_returns_200(self, client):
        resp = self._track(client, "vintage%20denim")
        assert resp.status_code == 200

    def test_track_keyword_response_shape(self, client):
        resp = self._track(client, "velvet%20blazer")
        data = resp.json()
        assert data["keyword"] == "velvet blazer"
        assert data["status"] == "tracking"

    def test_list_keywords_returns_200(self, client):
        resp = client.get("/api/trends/keywords/list")
        assert resp.status_code == 200
        assert "keywords" in resp.json()

    def test_tracked_keyword_appears_in_list(self, client):
        self._track(client, "linen%20trousers")
        resp = client.get("/api/trends/keywords/list")
        keywords = [k["keyword"] for k in resp.json()["keywords"]]
        assert "linen trousers" in keywords

    def test_remove_keyword_returns_200(self, client):
        self._track(client, "removeme")
        resp = client.delete("/api/trends/keywords/removeme")
        assert resp.status_code == 200

    def test_removed_keyword_not_in_list(self, client):
        self._track(client, "gone%20soon")
        client.delete("/api/trends/keywords/gone%20soon")
        resp = client.get("/api/trends/keywords/list")
        active = [
            k["keyword"]
            for k in resp.json()["keywords"]
            if k.get("status") == "active"
        ]
        assert "gone soon" not in active

    def test_cannot_remove_seed_keyword(self, client, tmp_db):
        """Seed keywords are protected — DELETE must be rejected."""
        # Insert a seed keyword directly into the DB
        with patch("app.database.DB_PATH", tmp_db):
            from app.database import get_connection
            conn = get_connection()
            conn.execute(
                "INSERT OR IGNORE INTO keywords (keyword, source, status) "
                "VALUES ('vintage denim', 'seed', 'active')"
            )
            conn.commit()
            conn.close()
        resp = client.delete("/api/trends/keywords/vintage%20denim")
        assert resp.status_code == 403


# ── /api/trends/search ───────────────────────────────────────────────────────

class TestTrendSearch:
    def test_search_known_keyword_returns_200(self, client, tmp_db):
        """Insert pre-existing data so search returns immediately without scraping."""
        from datetime import datetime, timezone

        with patch("app.database.DB_PATH", tmp_db):
            from app.database import get_connection
            conn = get_connection()
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT OR IGNORE INTO keywords (keyword, source, status) VALUES (?, 'seed', 'active')",
                ("corduroy",),
            )
            conn.execute(
                "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) VALUES (?, 'google_trends', 'search_volume', 55.0, ?)",
                ("corduroy", now),
            )
            conn.commit()
            conn.close()

        with patch("app.scheduler.jobs.scrape_single_keyword"):
            resp = client.get("/api/trends/search?keyword=corduroy")
        assert resp.status_code == 200
        assert "keyword" in resp.json()

    def test_search_response_contains_score_field(self, client, tmp_db):
        with patch("app.scheduler.jobs.scrape_single_keyword"):
            resp = client.get("/api/trends/search?keyword=tweed")
        assert resp.status_code == 200
        assert "score" in resp.json()


# ── /api/trends/ranking-forecast ─────────────────────────────────────────────

class TestRankingForecast:
    def test_returns_top10_and_challengers(self, client):
        resp = client.get("/api/trends/ranking-forecast?period=7")
        assert resp.status_code == 200
        data = resp.json()
        assert "top10" in data
        assert "challengers" in data

    def test_horizon_days_is_7(self, client):
        resp = client.get("/api/trends/ranking-forecast")
        assert resp.json()["horizon_days"] == 7


# ── /api/trends/{keyword}/details ────────────────────────────────────────────

class TestTrendDetails:
    def test_details_for_tracked_keyword(self, client, tmp_db):
        """Seed some data then request details for that keyword."""
        from datetime import datetime, timezone, timedelta

        with patch("app.database.DB_PATH", tmp_db):
            from app.database import get_connection
            conn = get_connection()
            conn.execute(
                "INSERT OR IGNORE INTO keywords (keyword, source, status) VALUES ('wool coat', 'seed', 'active')"
            )
            for i in range(10):
                date = (datetime.now(timezone.utc) - timedelta(days=i * 7)).strftime(
                    "%Y-%m-%dT00:00:00"
                )
                conn.execute(
                    "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) "
                    "VALUES ('wool coat', 'google_trends', 'search_volume', ?, ?)",
                    (float(40 + i * 3), date),
                )
            conn.commit()
            conn.close()

        resp = client.get("/api/trends/wool%20coat/details?period=30")
        assert resp.status_code == 200
        data = resp.json()
        assert "keyword" in data
        assert data["keyword"] == "wool coat"

    def test_details_response_has_search_volume_field(self, client):
        with patch("app.scheduler.jobs.scrape_single_keyword"):
            resp = client.get("/api/trends/blazer/details")
        assert resp.status_code == 200
        assert "search_volume" in resp.json()


# ── /api/trends/{keyword}/seasonal ───────────────────────────────────────────

class TestTrendSeasonal:
    def test_seasonal_returns_list(self, client):
        resp = client.get("/api/trends/vintage%20dress/seasonal")
        assert resp.status_code == 200
        data = resp.json()
        assert "seasonal" in data
        assert isinstance(data["seasonal"], (list, dict))


# ── /api/trends/{keyword}/images ─────────────────────────────────────────────

class TestTrendImages:
    def test_images_endpoint_returns_200(self, client):
        with patch("app.scrapers.pinterest.scrape_pinterest_images", return_value=[]):
            resp = client.get("/api/trends/vintage%20denim/images")
        assert resp.status_code == 200
        data = resp.json()
        assert "images" in data
        assert isinstance(data["images"], list)


# ── /api/trends/keywords/{keyword}/sourcing ──────────────────────────────────

class TestKeywordSourcing:
    def test_sourcing_returns_garments_list(self, client):
        mock_anthropic = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='{"garments": [{"item": "Leather blazer (1980s)", "why": "Core piece", '
                '"price_range": "$55-$95", "sourcing_tip": "Check estate sales"}]}'
            )
        ]
        mock_anthropic.return_value.messages.create.return_value = mock_response

        with patch("anthropic.Anthropic", mock_anthropic):
            resp = client.get("/api/trends/keywords/mob%20wife/sourcing")

        assert resp.status_code == 200
        data = resp.json()
        assert "garments" in data
        assert isinstance(data["garments"], list)

    def test_sourcing_garment_has_required_fields(self, client):
        mock_anthropic = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='{"garments": [{"item": "Silk blouse", "why": "Elegant", '
                '"price_range": "$20-$60", "sourcing_tip": "Thrift stores"}]}'
            )
        ]
        mock_anthropic.return_value.messages.create.return_value = mock_response

        with patch("anthropic.Anthropic", mock_anthropic):
            resp = client.get("/api/trends/keywords/quiet%20luxury/sourcing")

        garments = resp.json()["garments"]
        if garments:
            g = garments[0]
            for field in ("item", "why", "price_range", "sourcing_tip"):
                assert field in g
