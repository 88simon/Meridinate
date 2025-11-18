"""
Tests for wallets router

Tests multi-token wallet queries and balance refresh
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import analyzed_tokens_db as db


@pytest.mark.integration
class TestMultiTokenWallets:
    """Test multi-token wallet queries"""

    def test_get_multi_token_wallets_empty(self, test_client: TestClient, test_db: str):
        """Test getting multi-token wallets when database is empty"""
        response = test_client.get("/multi-token-wallets?min_tokens=2")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0
        assert data["wallets"] == []

    def test_get_multi_token_wallets(self, test_client: TestClient, test_db: str):
        """Test getting wallets that appear in multiple tokens"""
        # Create two tokens with overlapping wallet
        shared_wallet = "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"

        # Token 1
        db.save_analyzed_token(
            token_address="Token1Address1234567890123456789012345",
            token_name="Token 1",
            token_symbol="TK1",
            acronym="TK1",
            early_bidders=[
                {
                    "wallet_address": shared_wallet,
                    "first_buy_time": "2024-01-15T09:00:00",
                    "total_usd": 100.0,
                    "transaction_count": 1,
                    "average_buy_usd": 100.0,
                    "wallet_balance_usd": 1000.0,
                }
            ],
            axiom_json=[],
            credits_used=50,
            max_wallets=10,
        )

        # Token 2
        db.save_analyzed_token(
            token_address="Token2Address1234567890123456789012345",
            token_name="Token 2",
            token_symbol="TK2",
            acronym="TK2",
            early_bidders=[
                {
                    "wallet_address": shared_wallet,
                    "first_buy_time": "2024-01-16T09:00:00",
                    "total_usd": 150.0,
                    "transaction_count": 2,
                    "average_buy_usd": 75.0,
                    "wallet_balance_usd": 1500.0,
                }
            ],
            axiom_json=[],
            credits_used=50,
            max_wallets=10,
        )

        # Query multi-token wallets
        response = test_client.get("/multi-token-wallets?min_tokens=2")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] >= 1

        # Find the shared wallet
        wallet = next((w for w in data["wallets"] if w["wallet_address"] == shared_wallet), None)
        assert wallet is not None
        assert wallet["token_count"] >= 2

    def test_multi_token_wallets_caching(self, test_client: TestClient, test_db: str):
        """Test that multi-token wallets endpoint uses caching"""
        # First request
        response1 = test_client.get("/multi-token-wallets?min_tokens=2")
        assert response1.status_code == 200

        # Second request (should be cached)
        response2 = test_client.get("/multi-token-wallets?min_tokens=2")
        assert response2.status_code == 200

        # Results should be identical
        assert response1.json() == response2.json()


@pytest.mark.integration
class TestBalanceRefresh:
    """Test wallet balance refresh functionality"""

    @patch("requests.get")
    def test_refresh_wallet_balances(self, mock_get, test_client: TestClient):
        """Test refreshing wallet balances"""
        # Mock Helius API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"nativeBalance": 5000000}
        mock_get.return_value = mock_response

        payload = {"wallet_addresses": ["DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"]}

        response = test_client.post("/wallets/refresh-balances", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["total_wallets"] == 1
        assert data["successful"] >= 0
        assert "results" in data

    def test_refresh_balances_empty_list(self, test_client: TestClient):
        """Test refreshing with empty wallet list"""
        payload = {"wallet_addresses": []}

        response = test_client.post("/wallets/refresh-balances", json=payload)
        assert response.status_code == 422  # Validation error (min_items=1)

    @patch("requests.get")
    def test_refresh_multiple_balances(self, mock_get, test_client: TestClient):
        """Test refreshing multiple wallet balances"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"nativeBalance": 1000000}
        mock_get.return_value = mock_response

        payload = {
            "wallet_addresses": [
                "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK",
                "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku",
            ]
        }

        response = test_client.post("/wallets/refresh-balances", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["total_wallets"] == 2
        assert len(data["results"]) == 2
