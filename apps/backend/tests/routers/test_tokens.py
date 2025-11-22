"""
Tests for tokens router

Tests token CRUD operations, trash management, and history tracking
"""

import pytest
from fastapi.testclient import TestClient

from meridinate import analyzed_tokens_db as db


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


@pytest.mark.integration
class TestTokenTags:
    """Test token tagging system (GEM/DUD classification)"""

    def test_get_empty_token_tags(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test getting tags for a token with no tags"""
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

        response = test_client.get(f"/api/tokens/{token_id}/tags")
        assert response.status_code == 200

        data = response.json()
        assert "tags" in data
        assert data["tags"] == []

    def test_add_gem_tag(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test adding a 'gem' tag to a token"""
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

        # Add gem tag
        response = test_client.post(f"/api/tokens/{token_id}/tags", json={"tag": "gem"})
        assert response.status_code == 200
        assert "message" in response.json()

        # Verify tag was added
        response = test_client.get(f"/api/tokens/{token_id}/tags")
        data = response.json()
        assert "gem" in data["tags"]

    def test_add_dud_tag(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test adding a 'dud' tag to a token"""
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

        # Add dud tag
        response = test_client.post(f"/api/tokens/{token_id}/tags", json={"tag": "dud"})
        assert response.status_code == 200

        # Verify tag was added
        response = test_client.get(f"/api/tokens/{token_id}/tags")
        data = response.json()
        assert "dud" in data["tags"]

    def test_add_duplicate_tag(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test adding duplicate tag returns error"""
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

        # Add gem tag
        test_client.post(f"/api/tokens/{token_id}/tags", json={"tag": "gem"})

        # Try to add same tag again
        response = test_client.post(f"/api/tokens/{token_id}/tags", json={"tag": "gem"})
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower()

    def test_remove_tag(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test removing a tag from a token"""
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

        # Add gem tag
        test_client.post(f"/api/tokens/{token_id}/tags", json={"tag": "gem"})

        # Remove gem tag
        response = test_client.request("DELETE", f"/api/tokens/{token_id}/tags", json={"tag": "gem"})
        assert response.status_code == 200

        # Verify tag was removed
        response = test_client.get(f"/api/tokens/{token_id}/tags")
        data = response.json()
        assert "gem" not in data["tags"]

    def test_remove_nonexistent_tag(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test removing a tag that doesn't exist (should succeed silently)"""
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

        # Remove tag that doesn't exist
        response = test_client.request("DELETE", f"/api/tokens/{token_id}/tags", json={"tag": "gem"})
        assert response.status_code == 200

    def test_tags_in_token_history(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test that tags appear in token history endpoint"""
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

        # Add gem tag
        test_client.post(f"/api/tokens/{token_id}/tags", json={"tag": "gem"})

        # Get token history
        response = test_client.get("/api/tokens/history")
        data = response.json()

        # Find our token
        token = next((t for t in data["tokens"] if t["id"] == token_id), None)
        assert token is not None
        assert "tags" in token
        assert "gem" in token["tags"]

    def test_tags_in_token_detail(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test that tags appear in token detail endpoint"""
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

        # Add dud tag
        test_client.post(f"/api/tokens/{token_id}/tags", json={"tag": "dud"})

        # Get token detail
        response = test_client.get(f"/api/tokens/{token_id}")
        data = response.json()

        assert "tags" in data
        assert "dud" in data["tags"]

    def test_multiple_tags(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test adding multiple different tags to a token"""
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

        # Add multiple tags
        test_client.post(f"/api/tokens/{token_id}/tags", json={"tag": "gem"})
        test_client.post(f"/api/tokens/{token_id}/tags", json={"tag": "trending"})

        # Verify both tags exist
        response = test_client.get(f"/api/tokens/{token_id}/tags")
        data = response.json()
        assert "gem" in data["tags"]
        assert "trending" in data["tags"]

    def test_cache_invalidation_on_tag_add(self, test_client: TestClient, test_db: str, sample_token_data, sample_early_bidders):
        """Test that adding a tag invalidates the tokens cache"""
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

        # Get initial history (caches result)
        response1 = test_client.get("/api/tokens/history")
        etag1 = response1.headers.get("etag")

        # Add tag (should invalidate cache)
        test_client.post(f"/api/tokens/{token_id}/tags", json={"tag": "gem"})

        # Get history again (should have new ETag)
        response2 = test_client.get("/api/tokens/history")
        etag2 = response2.headers.get("etag")

        # ETags should be different after tag was added
        assert etag1 != etag2
