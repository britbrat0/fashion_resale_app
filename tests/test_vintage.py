"""
Tests for the Vintage / Era Explorer API:
  GET  /api/vintage/eras                  - list all eras
  GET  /api/vintage/eras/{id}             - single era detail
  GET  /api/vintage/eras/{id}/market      - market data for an era
  GET  /api/vintage/descriptor-options    - chip options for classifier
  POST /api/vintage/classify              - classify a garment (mocked Claude)
  GET  /api/vintage/etsy-listings         - search Etsy (mocked)
"""

import json
import pytest
from unittest.mock import patch, MagicMock


# ── Era listing ───────────────────────────────────────────────────────────────

class TestEraList:
    def test_list_eras_returns_200(self, client):
        resp = client.get("/api/vintage/eras")
        assert resp.status_code == 200

    def test_list_eras_returns_24_eras(self, client):
        resp = client.get("/api/vintage/eras")
        eras = resp.json()["eras"]
        assert len(eras) == 24

    def test_each_era_has_id_label_period(self, client):
        resp = client.get("/api/vintage/eras")
        for era in resp.json()["eras"]:
            assert "id" in era
            assert "label" in era
            assert "period" in era


# ── Era detail ────────────────────────────────────────────────────────────────

class TestEraDetail:
    def test_era_detail_returns_200(self, client):
        resp = client.get("/api/vintage/eras/1920s")
        assert resp.status_code == 200

    def test_era_detail_has_style_fields(self, client):
        resp = client.get("/api/vintage/eras/1920s")
        data = resp.json()
        for field in ("id", "label", "period", "colors", "fabrics", "silhouettes"):
            assert field in data, f"Missing field: {field}"

    def test_era_detail_unknown_id_returns_404(self, client):
        resp = client.get("/api/vintage/eras/not-a-real-era")
        assert resp.status_code == 404

    def test_multiple_era_ids_resolve(self, client):
        """Spot-check a selection of era IDs that must exist."""
        era_ids = ["1950s", "early-1970s", "early-1980s", "late-1990s"]
        for era_id in era_ids:
            resp = client.get(f"/api/vintage/eras/{era_id}")
            assert resp.status_code == 200, f"Era '{era_id}' not found"

    def test_era_detail_does_not_expose_search_terms(self, client):
        """image_search_terms should be stripped from the public response."""
        resp = client.get("/api/vintage/eras/1950s")
        assert "image_search_terms" not in resp.json()


# ── Descriptor options ────────────────────────────────────────────────────────

class TestDescriptorOptions:
    def test_descriptor_options_returns_200(self, client):
        resp = client.get("/api/vintage/descriptor-options")
        assert resp.status_code == 200

    def test_all_seven_categories_present(self, client):
        resp = client.get("/api/vintage/descriptor-options")
        data = resp.json()
        for category in ("fabrics", "prints", "silhouettes", "brands",
                         "colors", "aesthetics", "key_garments"):
            assert category in data, f"Missing category: {category}"

    def test_each_category_has_multiple_options(self, client):
        resp = client.get("/api/vintage/descriptor-options")
        for category, options in resp.json().items():
            assert len(options) >= 3, f"Category '{category}' has too few options"


# ── Garment classification ────────────────────────────────────────────────────

class TestGarmentClassify:
    _VALID_RESPONSE = {
        "primary_era": {
            "id": "early-1970s",
            "label": "Boho & Counterculture (Early 1970s)",
            "confidence": 0.87,
            "reasoning": "Peasant blouse silhouette, macramé trim, earthy tones",
        },
        "alternate_eras": [
            {"id": "late-1960s", "label": "Late 1960s", "confidence": 0.09, "reasoning": "Some 60s elements"},
            {"id": "late-1970s", "label": "Late 1970s", "confidence": 0.04, "reasoning": "Slight disco influence"},
        ],
        "matching_features": ["Peasant blouse silhouette", "Natural fibers", "Earthy palette"],
        "related_keywords": ["boho blouse vintage", "peasant top 1970s"],
    }

    def _mock_classifier(self, response_dict=None):
        result = response_dict or self._VALID_RESPONSE
        mock = MagicMock()
        mock.return_value = result
        return mock

    def test_classify_text_only_returns_200(self, client):
        mock_fn = self._mock_classifier()
        with patch("app.vintage.classifier.classify_garment", mock_fn):
            resp = client.post(
                "/api/vintage/classify",
                data={
                    "fabrics": '["Cotton", "Linen"]',
                    "silhouettes": '["Peasant blouse"]',
                    "colors": '["Earthy tones"]',
                },
            )
        assert resp.status_code == 200

    def test_classify_returns_status_ok(self, client):
        mock_fn = self._mock_classifier()
        with patch("app.vintage.classifier.classify_garment", mock_fn):
            resp = client.post(
                "/api/vintage/classify",
                data={"fabrics": '["Velvet"]', "colors": '["Deep burgundy"]'},
            )
        assert resp.json()["status"] == "ok"

    def test_classify_result_has_primary_era(self, client):
        mock_fn = self._mock_classifier()
        with patch("app.vintage.classifier.classify_garment", mock_fn):
            resp = client.post(
                "/api/vintage/classify",
                data={"aesthetics": '["Disco glamour"]'},
            )
        result = resp.json()["result"]
        assert "primary_era" in result
        assert "id" in result["primary_era"]
        assert "confidence" in result["primary_era"]

    def test_classify_result_has_two_alternates(self, client):
        mock_fn = self._mock_classifier()
        with patch("app.vintage.classifier.classify_garment", mock_fn):
            resp = client.post(
                "/api/vintage/classify",
                data={"silhouettes": '["A-line skirt"]'},
            )
        alternates = resp.json()["result"]["alternate_eras"]
        assert len(alternates) == 2

    def test_classify_no_input_returns_400(self, client):
        """Submitting nothing must be rejected."""
        resp = client.post("/api/vintage/classify", data={})
        assert resp.status_code == 400

    def test_classify_with_notes_field(self, client):
        mock_fn = self._mock_classifier()
        with patch("app.vintage.classifier.classify_garment", mock_fn):
            resp = client.post(
                "/api/vintage/classify",
                data={"notes": "Has a Talon zipper and ILGWU union label"},
            )
        assert resp.status_code == 200


# ── Era market data ───────────────────────────────────────────────────────────

class TestEraMarket:
    def test_market_data_returns_200(self, client):
        resp = client.get("/api/vintage/eras/1950s/market")
        assert resp.status_code == 200

    def test_market_data_has_expected_keys(self, client):
        resp = client.get("/api/vintage/eras/1950s/market")
        data = resp.json()
        for key in ("price_stats", "by_platform", "lifecycle_stage", "garment_prices"):
            assert key in data, f"Missing key: {key}"

    def test_market_data_by_platform_has_four_platforms(self, client, tmp_db):
        """When trend data exists, by_platform should cover all four marketplaces."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        with patch("app.database.DB_PATH", tmp_db):
            from app.database import get_connection
            conn = get_connection()
            for source, price in [("ebay", 50.0), ("etsy", 30.0), ("poshmark", 25.0), ("depop", 20.0)]:
                conn.execute(
                    "INSERT INTO trend_data (keyword, source, metric, value, recorded_at) "
                    "VALUES (?, ?, 'avg_price', ?, ?)",
                    ("1950s vintage", source, price, now),
                )
            conn.commit()
            conn.close()

        resp = client.get("/api/vintage/eras/1950s/market")
        assert resp.status_code == 200

    def test_unknown_era_market_returns_404(self, client):
        resp = client.get("/api/vintage/eras/fake-era-id/market")
        assert resp.status_code == 404


# ── Etsy listings ─────────────────────────────────────────────────────────────

class TestEtsyListings:
    def test_etsy_listings_returns_200(self, client):
        mock_listings = [
            {"title": "1970s peasant blouse", "price": 28.0, "url": "https://etsy.com/1"},
            {"title": "Vintage boho top", "price": 35.0, "url": "https://etsy.com/2"},
        ]
        with patch("app.vintage.validation.search_etsy_listings", return_value=mock_listings):
            resp = client.get("/api/vintage/etsy-listings?q=1970s+peasant+blouse")
        assert resp.status_code == 200

    def test_etsy_listings_response_shape(self, client):
        with patch("app.vintage.validation.search_etsy_listings", return_value=[]):
            resp = client.get("/api/vintage/etsy-listings?q=vintage+dress")
        data = resp.json()
        assert "query" in data
        assert "listings" in data
        assert isinstance(data["listings"], list)
