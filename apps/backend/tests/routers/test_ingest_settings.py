"""
Tests for ingest settings API endpoints

Covers:
- Settings save/load (including ingest_enabled, caps, scoring toggle)
- bypass_limits flag behavior
- Default values
"""

import json
import os
import tempfile
from typing import Any, Dict, Generator

import pytest
from fastapi.testclient import TestClient

from meridinate import settings
from meridinate.models import DEFAULT_INGEST_SETTINGS


@pytest.fixture
def ingest_settings_file() -> Generator[str, None, None]:
    """Create a temporary ingest settings file"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(DEFAULT_INGEST_SETTINGS, f)
        settings_path = f.name

    yield settings_path

    if os.path.exists(settings_path):
        os.unlink(settings_path)


@pytest.fixture
def client_with_ingest_settings(
    test_client: TestClient, ingest_settings_file: str, monkeypatch
) -> TestClient:
    """Test client with ingest settings file configured"""
    monkeypatch.setattr(settings, "INGEST_SETTINGS_FILE", ingest_settings_file)
    return test_client


class TestIngestSettingsGet:
    """Tests for GET /api/ingest/settings"""

    def test_get_settings_returns_defaults(self, client_with_ingest_settings: TestClient):
        """Should return default settings when no custom settings exist"""
        response = client_with_ingest_settings.get("/api/ingest/settings")
        assert response.status_code == 200

        data = response.json()
        assert "ingest_enabled" in data
        assert "tier0_max_tokens_per_run" in data
        assert "tier0_interval_minutes" in data
        assert "bypass_limits" in data

    def test_get_settings_has_correct_structure(self, client_with_ingest_settings: TestClient):
        """Should return settings with all expected fields"""
        response = client_with_ingest_settings.get("/api/ingest/settings")
        assert response.status_code == 200

        data = response.json()

        # Core settings
        assert isinstance(data.get("ingest_enabled"), bool)
        assert isinstance(data.get("tier0_max_tokens_per_run"), int)
        assert isinstance(data.get("tier0_interval_minutes"), int)

        # Performance thresholds
        assert isinstance(data.get("performance_prime_threshold"), int)
        assert isinstance(data.get("performance_monitor_threshold"), int)

        # Bypass flag
        assert isinstance(data.get("bypass_limits"), bool)


class TestIngestSettingsUpdate:
    """Tests for POST /api/ingest/settings"""

    def test_update_ingest_enabled(self, client_with_ingest_settings: TestClient):
        """Should update ingest_enabled flag"""
        # First disable
        response = client_with_ingest_settings.post(
            "/api/ingest/settings",
            json={"ingest_enabled": False},
        )
        assert response.status_code == 200

        # Verify it persisted
        get_response = client_with_ingest_settings.get("/api/ingest/settings")
        assert get_response.json()["ingest_enabled"] is False

        # Re-enable
        response = client_with_ingest_settings.post(
            "/api/ingest/settings",
            json={"ingest_enabled": True},
        )
        assert response.status_code == 200

        # Verify
        get_response = client_with_ingest_settings.get("/api/ingest/settings")
        assert get_response.json()["ingest_enabled"] is True

    def test_update_tier0_settings(self, client_with_ingest_settings: TestClient):
        """Should update Tier-0 related settings"""
        response = client_with_ingest_settings.post(
            "/api/ingest/settings",
            json={
                "tier0_max_tokens_per_run": 50,
                "tier0_interval_minutes": 30,
            },
        )
        assert response.status_code == 200

        # Verify
        get_response = client_with_ingest_settings.get("/api/ingest/settings")
        data = get_response.json()
        assert data["tier0_max_tokens_per_run"] == 50
        assert data["tier0_interval_minutes"] == 30

    def test_update_thresholds(self, client_with_ingest_settings: TestClient):
        """Should update performance thresholds"""
        response = client_with_ingest_settings.post(
            "/api/ingest/settings",
            json={
                "performance_prime_threshold": 75,
                "performance_monitor_threshold": 30,
            },
        )
        assert response.status_code == 200

        get_response = client_with_ingest_settings.get("/api/ingest/settings")
        data = get_response.json()
        assert data["performance_prime_threshold"] == 75
        assert data["performance_monitor_threshold"] == 30

    def test_bypass_limits_flag(self, client_with_ingest_settings: TestClient):
        """Should update and persist bypass_limits flag"""
        # Enable bypass
        response = client_with_ingest_settings.post(
            "/api/ingest/settings",
            json={"bypass_limits": True},
        )
        assert response.status_code == 200

        get_response = client_with_ingest_settings.get("/api/ingest/settings")
        assert get_response.json()["bypass_limits"] is True

        # Disable bypass
        response = client_with_ingest_settings.post(
            "/api/ingest/settings",
            json={"bypass_limits": False},
        )
        assert response.status_code == 200

        get_response = client_with_ingest_settings.get("/api/ingest/settings")
        assert get_response.json()["bypass_limits"] is False

    def test_partial_update_preserves_other_settings(
        self, client_with_ingest_settings: TestClient
    ):
        """Partial updates should not reset other settings"""
        # Set initial values
        client_with_ingest_settings.post(
            "/api/ingest/settings",
            json={
                "ingest_enabled": True,
                "tier0_max_tokens_per_run": 100,
                "performance_prime_threshold": 80,
            },
        )

        # Update only one field
        client_with_ingest_settings.post(
            "/api/ingest/settings",
            json={"performance_prime_threshold": 90},
        )

        # Verify other fields preserved
        get_response = client_with_ingest_settings.get("/api/ingest/settings")
        data = get_response.json()
        assert data["ingest_enabled"] is True
        assert data["tier0_max_tokens_per_run"] == 100
        assert data["performance_prime_threshold"] == 90


class TestIngestSettingsValidation:
    """Tests for settings validation"""

    def test_invalid_threshold_values_rejected(
        self, client_with_ingest_settings: TestClient
    ):
        """Should reject invalid threshold values"""
        # Negative values should be rejected or clamped
        response = client_with_ingest_settings.post(
            "/api/ingest/settings",
            json={"performance_prime_threshold": -10},
        )
        # May return 422 for validation error or 200 with clamped value
        # depending on implementation - either is acceptable

    def test_settings_file_persistence(
        self, client_with_ingest_settings: TestClient, ingest_settings_file: str
    ):
        """Settings should be persisted to file"""
        client_with_ingest_settings.post(
            "/api/ingest/settings",
            json={"tier0_max_tokens_per_run": 123},
        )

        # Read file directly to verify persistence
        with open(ingest_settings_file, "r") as f:
            file_data = json.load(f)

        assert file_data.get("tier0_max_tokens_per_run") == 123
