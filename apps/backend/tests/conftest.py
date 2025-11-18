"""
Pytest fixtures and configuration for Gun Del Sol tests

Provides shared fixtures for all test modules
"""

import json
import os
import sqlite3
import tempfile
from typing import Any, Dict, Generator

import pytest
from fastapi.testclient import TestClient

from app import settings, state

# Import the app
from app.main import create_app


@pytest.fixture(scope="function")
def test_db_path() -> Generator[str, None, None]:
    """Create a temporary test database for each test"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        db_path = f.name

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        try:
            os.unlink(db_path)
        except:
            pass  # File might be locked on Windows


@pytest.fixture(scope="function")
def test_db(test_db_path: str) -> Generator[str, None, None]:
    """
    Initialize test database with schema for each test

    This fixture has function scope so each test gets a fresh database
    """
    # Import database module to initialize schema
    import analyzed_tokens_db as db

    # Temporarily override the database path
    original_db_path = db.DATABASE_FILE
    db.DATABASE_FILE = test_db_path

    # Initialize the database schema
    db.init_database()

    yield test_db_path

    # Restore original path
    db.DATABASE_FILE = original_db_path

    # No need to clean up rows - each test gets a new database file


@pytest.fixture(scope="function")
def test_client(test_db: str, monkeypatch) -> Generator[TestClient, None, None]:
    """
    Create a test client with test database

    This fixture provides a FastAPI TestClient configured for testing
    """
    # Override settings to use test database
    monkeypatch.setattr(settings, "DATABASE_FILE", test_db)

    # Create temporary files for test data
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        test_data_file = f.name
        json.dump({}, f)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        test_settings_file = f.name
        json.dump(settings.DEFAULT_API_SETTINGS, f)

    # Override file paths
    monkeypatch.setattr(settings, "DATA_FILE", test_data_file)
    monkeypatch.setattr(settings, "SETTINGS_FILE", test_settings_file)

    # Clear in-memory state
    state.monitored_addresses.clear()
    state.analysis_jobs.clear()

    # Clear all router caches before each test
    from app.routers import tags, tokens, wallets

    tokens.cache.cache.clear()
    tokens.cache.pending_requests.clear()
    tags.cache.cache.clear()
    tags.cache.pending_requests.clear()
    wallets.cache.cache.clear()
    wallets.cache.pending_requests.clear()

    # Create app and client
    app = create_app()
    client = TestClient(app)

    yield client

    # Cleanup temp files
    if os.path.exists(test_data_file):
        os.unlink(test_data_file)
    if os.path.exists(test_settings_file):
        os.unlink(test_settings_file)


@pytest.fixture
def sample_token_data() -> Dict[str, Any]:
    """Sample token data for testing"""
    return {
        "token_address": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
        "token_name": "Test Token",
        "token_symbol": "TEST",
        "acronym": "TT",
        "analysis_timestamp": "2024-01-15T10:00:00",
        "first_buy_timestamp": "2024-01-15T09:00:00",
        "wallets_found": 5,
    }


@pytest.fixture
def sample_wallet_address() -> str:
    """Sample Solana wallet address for testing"""
    return "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"


@pytest.fixture
def sample_early_bidders() -> list:
    """Sample early bidder data for testing"""
    return [
        {
            "wallet_address": "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK",
            "first_buy_time": "2024-01-15T09:01:00",
            "total_usd": 150.0,
            "transaction_count": 3,
            "average_buy_usd": 50.0,
            "wallet_balance_usd": 1000.0,
        },
        {
            "wallet_address": "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku",
            "first_buy_time": "2024-01-15T09:02:00",
            "total_usd": 200.0,
            "transaction_count": 2,
            "average_buy_usd": 100.0,
            "wallet_balance_usd": 2000.0,
        },
    ]


@pytest.fixture
def sample_analysis_settings() -> Dict[str, Any]:
    """Sample analysis settings for testing"""
    return {
        "transactionLimit": 500,
        "minUsdFilter": 50.0,
        "walletCount": 10,
        "apiRateDelay": 100,
        "maxCreditsPerAnalysis": 1000,
        "maxRetries": 3,
    }


@pytest.fixture
def mock_helius_response() -> Dict[str, Any]:
    """Mock Helius API response for testing"""
    return {
        "token_address": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
        "token_info": {"onChainMetadata": {"metadata": {"name": "Test Token", "symbol": "TEST"}}},
        "first_transaction_time": "2024-01-15T09:00:00",
        "early_bidders": [
            {
                "wallet_address": "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK",
                "first_buy_time": "2024-01-15T09:01:00",
                "total_usd": 150.0,
                "transaction_count": 3,
                "average_buy_usd": 50.0,
            }
        ],
        "total_unique_buyers": 1,
        "total_transactions_analyzed": 100,
        "api_credits_used": 50,
    }
