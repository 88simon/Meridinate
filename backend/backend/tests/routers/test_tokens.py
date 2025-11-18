"""
Tests for tokens router

Tests token CRUD operations, trash management, and history tracking
"""

import pytest
from fastapi.testclient import TestClient

import analyzed_tokens_db as db


@pytest.mark.integration
class TestTokensHistory:
    """Test token history and listing endpoints"""

    def test_get_empty_tokens_history(self, test_client: TestClient, test_db: str):
        """Test getting tokens when database is empty"""
        response = test_client.get("/api/tokens/history")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0
        assert data["total_wallets"] == 0
        assert data["tokens"] == []

    def test_get_tokens_history(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test getting tokens history with data"""
        # Save a token to database
        token_id = db.save_analyzed_token(
            token_address=sample_token_data["token_address"],
            token_name=sample_token_data["token_name"],
            token_symbol=sample_token_data["token_symbol"],
            acronym=sample_token_data["acronym"],
            early_bidders=sample_early_bidders,
            axiom_json=[],
            credits_used=50,
            max_wallets=10,
        )

        response = test_client.get("/api/tokens/history")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] >= 1
        assert data["total_wallets"] >= len(sample_early_bidders)
        assert len(data["tokens"]) >= 1

        # Check first token
        token = data["tokens"][0]
        assert token["token_name"] == sample_token_data["token_name"]
        assert token["token_symbol"] == sample_token_data["token_symbol"]

    def test_tokens_history_caching(self, test_client: TestClient, test_db: str):
        """Test that tokens history endpoint uses caching"""
        # First request
        response1 = test_client.get("/api/tokens/history")
        etag1 = response1.headers.get("etag")

        # Second request should return same ETag
        response2 = test_client.get("/api/tokens/history")
        etag2 = response2.headers.get("etag")

        assert etag1 == etag2

    def test_tokens_history_conditional_request(self, test_client: TestClient, test_db: str):
        """Test conditional requests with If-None-Match"""
        # Get initial response
        response = test_client.get("/api/tokens/history")
        etag = response.headers.get("etag")

        # Make conditional request
        response = test_client.get("/api/tokens/history", headers={"If-None-Match": etag})
        assert response.status_code == 304  # Not Modified


@pytest.mark.integration
class TestTokenDetails:
    """Test token detail endpoints"""

    def test_get_token_by_id(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test getting token details by ID"""
        token_id = db.save_analyzed_token(
            token_address=sample_token_data["token_address"],
            token_name=sample_token_data["token_name"],
            token_symbol=sample_token_data["token_symbol"],
            acronym=sample_token_data["acronym"],
            early_bidders=sample_early_bidders,
            axiom_json=[{"wallet": "test"}],
            credits_used=50,
            max_wallets=10,
        )

        response = test_client.get(f"/api/tokens/{token_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == token_id
        assert data["token_name"] == sample_token_data["token_name"]
        assert "wallets" in data
        assert "axiom_json" in data
        assert len(data["wallets"]) == len(sample_early_bidders)

    def test_get_nonexistent_token(self, test_client: TestClient, test_db: str):
        """Test getting token that doesn't exist"""
        response = test_client.get("/api/tokens/99999")
        assert response.status_code == 404

    def test_get_token_analysis_history(
        self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders
    ):
        """Test getting analysis history for a token"""
        token_id = db.save_analyzed_token(
            token_address=sample_token_data["token_address"],
            token_name=sample_token_data["token_name"],
            token_symbol=sample_token_data["token_symbol"],
            acronym=sample_token_data["acronym"],
            early_bidders=sample_early_bidders,
            axiom_json=[],
            credits_used=50,
            max_wallets=10,
        )

        response = test_client.get(f"/api/tokens/{token_id}/history")
        assert response.status_code == 200

        data = response.json()
        assert data["token_id"] == token_id
        assert "total_runs" in data
        assert "runs" in data
        assert data["total_runs"] >= 1


@pytest.mark.integration
class TestTokenTrash:
    """Test token trash/soft delete functionality"""

    def test_soft_delete_token(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test soft deleting a token"""
        token_id = db.save_analyzed_token(
            token_address=sample_token_data["token_address"],
            token_name=sample_token_data["token_name"],
            token_symbol=sample_token_data["token_symbol"],
            acronym=sample_token_data["acronym"],
            early_bidders=sample_early_bidders,
            axiom_json=[],
            credits_used=50,
            max_wallets=10,
        )

        # Delete token
        response = test_client.delete(f"/api/tokens/{token_id}")
        assert response.status_code == 200

        # Verify it's not in main list
        response = test_client.get("/api/tokens/history")
        data = response.json()
        token_ids = [t["id"] for t in data["tokens"]]
        assert token_id not in token_ids

    def test_get_deleted_tokens(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test getting trash (deleted tokens)"""
        token_id = db.save_analyzed_token(
            token_address=sample_token_data["token_address"],
            token_name=sample_token_data["token_name"],
            token_symbol=sample_token_data["token_symbol"],
            acronym=sample_token_data["acronym"],
            early_bidders=sample_early_bidders,
            axiom_json=[],
            credits_used=50,
            max_wallets=10,
        )

        # Delete token
        test_client.delete(f"/api/tokens/{token_id}")

        # Get trash
        response = test_client.get("/api/tokens/trash")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] >= 1
        token_ids = [t["id"] for t in data["tokens"]]
        assert token_id in token_ids

    def test_restore_token(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test restoring a deleted token"""
        token_id = db.save_analyzed_token(
            token_address=sample_token_data["token_address"],
            token_name=sample_token_data["token_name"],
            token_symbol=sample_token_data["token_symbol"],
            acronym=sample_token_data["acronym"],
            early_bidders=sample_early_bidders,
            axiom_json=[],
            credits_used=50,
            max_wallets=10,
        )

        # Delete token
        test_client.delete(f"/api/tokens/{token_id}")

        # Restore token
        response = test_client.post(f"/api/tokens/{token_id}/restore")
        assert response.status_code == 200

        # Verify it's back in main list
        response = test_client.get("/api/tokens/history")
        data = response.json()
        token_ids = [t["id"] for t in data["tokens"]]
        assert token_id in token_ids

    def test_permanent_delete_token(
        self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders
    ):
        """Test permanently deleting a token"""
        token_id = db.save_analyzed_token(
            token_address=sample_token_data["token_address"],
            token_name=sample_token_data["token_name"],
            token_symbol=sample_token_data["token_symbol"],
            acronym=sample_token_data["acronym"],
            early_bidders=sample_early_bidders,
            axiom_json=[],
            credits_used=50,
            max_wallets=10,
        )

        # Soft delete first
        test_client.delete(f"/api/tokens/{token_id}")

        # Permanent delete
        response = test_client.delete(f"/api/tokens/{token_id}/permanent")
        assert response.status_code == 200

        # Verify it's gone from trash too
        response = test_client.get("/api/tokens/trash")
        data = response.json()
        token_ids = [t["id"] for t in data["tokens"]]
        assert token_id not in token_ids
