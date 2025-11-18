"""
Tests for tags router

Tests wallet tagging and Codex functionality
"""

import pytest
from fastapi.testclient import TestClient

import analyzed_tokens_db as db


@pytest.mark.integration
class TestWalletTags:
    """Test wallet tagging endpoints"""

    def test_get_tags_for_new_wallet(self, test_client: TestClient, test_db: str, sample_wallet_address: str):
        """Test getting tags for a wallet that has no tags"""
        response = test_client.get(f"/wallets/{sample_wallet_address}/tags")
        assert response.status_code == 200

        data = response.json()
        assert data["tags"] == []

    def test_add_tag_to_wallet(self, test_client: TestClient, test_db: str, sample_wallet_address: str):
        """Test adding a tag to a wallet"""
        payload = {"tag": "whale", "is_kol": False}

        response = test_client.post(f"/wallets/{sample_wallet_address}/tags", json=payload)
        assert response.status_code == 200

        # Verify tag was added
        response = test_client.get(f"/wallets/{sample_wallet_address}/tags")
        data = response.json()
        assert len(data["tags"]) == 1
        assert data["tags"][0]["tag"] == "whale"
        assert data["tags"][0]["is_kol"] is False

    def test_add_kol_tag(self, test_client: TestClient, test_db: str, sample_wallet_address: str):
        """Test adding a KOL (Key Opinion Leader) tag"""
        payload = {"tag": "influencer", "is_kol": True}

        response = test_client.post(f"/wallets/{sample_wallet_address}/tags", json=payload)
        assert response.status_code == 200

        # Verify KOL flag
        response = test_client.get(f"/wallets/{sample_wallet_address}/tags")
        data = response.json()
        tag = next(t for t in data["tags"] if t["tag"] == "influencer")
        assert tag["is_kol"] is True

    def test_add_duplicate_tag(self, test_client: TestClient, test_db: str, sample_wallet_address: str):
        """Test adding the same tag twice"""
        payload = {"tag": "whale"}

        # First add
        response = test_client.post(f"/wallets/{sample_wallet_address}/tags", json=payload)
        assert response.status_code == 200

        # Second add (duplicate)
        response = test_client.post(f"/wallets/{sample_wallet_address}/tags", json=payload)
        assert response.status_code == 400

    def test_remove_tag_from_wallet(self, test_client: TestClient, test_db: str, sample_wallet_address: str):
        """Test removing a tag from a wallet"""
        # Add tag first
        test_client.post(f"/wallets/{sample_wallet_address}/tags", json={"tag": "whale"})

        # Remove tag using request() method which supports json parameter
        payload = {"tag": "whale"}
        response = test_client.request("DELETE", f"/wallets/{sample_wallet_address}/tags", json=payload)
        assert response.status_code == 200

        # Verify removal
        response = test_client.get(f"/wallets/{sample_wallet_address}/tags")
        data = response.json()
        assert len(data["tags"]) == 0

    def test_add_multiple_tags(self, test_client: TestClient, test_db: str, sample_wallet_address: str):
        """Test adding multiple tags to a wallet"""
        tags = ["whale", "early-adopter", "diamond-hands"]

        for tag in tags:
            test_client.post(f"/wallets/{sample_wallet_address}/tags", json={"tag": tag})

        # Get all tags
        response = test_client.get(f"/wallets/{sample_wallet_address}/tags")
        data = response.json()
        assert len(data["tags"]) == 3


@pytest.mark.integration
class TestTagQueries:
    """Test tag query endpoints"""

    def test_get_all_tags_empty(self, test_client: TestClient, test_db: str):
        """Test getting all tags when none exist"""
        response = test_client.get("/tags")
        assert response.status_code == 200

        data = response.json()
        assert data["tags"] == []

    def test_get_all_tags(self, test_client: TestClient, test_db: str):
        """Test getting all unique tags"""
        # Add tags to different wallets
        wallets = ["DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK", "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku"]

        test_client.post(f"/wallets/{wallets[0]}/tags", json={"tag": "whale"})
        test_client.post(f"/wallets/{wallets[1]}/tags", json={"tag": "whale"})
        test_client.post(f"/wallets/{wallets[1]}/tags", json={"tag": "early-adopter"})

        # Get all unique tags
        response = test_client.get("/tags")
        data = response.json()
        assert len(data["tags"]) >= 2
        assert "whale" in data["tags"]
        assert "early-adopter" in data["tags"]

    def test_get_wallets_by_tag(self, test_client: TestClient, test_db: str):
        """Test getting all wallets with a specific tag"""
        wallets = ["DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK", "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku"]

        # Tag both wallets
        for wallet in wallets:
            test_client.post(f"/wallets/{wallet}/tags", json={"tag": "whale"})

        # Get wallets by tag
        response = test_client.get("/tags/whale/wallets")
        assert response.status_code == 200

        data = response.json()
        assert data["tag"] == "whale"
        assert len(data["wallets"]) >= 2


@pytest.mark.integration
class TestCodex:
    """Test Codex (wallet directory) endpoints"""

    def test_get_codex_empty(self, test_client: TestClient, test_db: str):
        """Test getting Codex when no wallets have tags"""
        response = test_client.get("/codex")
        assert response.status_code == 200

        data = response.json()
        assert data["wallets"] == []

    def test_get_codex(self, test_client: TestClient, test_db: str):
        """Test getting Codex with tagged wallets"""
        # Tag some wallets
        wallet1 = "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"
        wallet2 = "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku"

        test_client.post(f"/wallets/{wallet1}/tags", json={"tag": "whale", "is_kol": False})
        test_client.post(f"/wallets/{wallet1}/tags", json={"tag": "early-adopter", "is_kol": False})
        test_client.post(f"/wallets/{wallet2}/tags", json={"tag": "influencer", "is_kol": True})

        # Get Codex
        response = test_client.get("/codex")
        assert response.status_code == 200

        data = response.json()
        assert len(data["wallets"]) >= 2

        # Verify wallet1 has correct tags
        wallet1_data = next(w for w in data["wallets"] if w["wallet_address"] == wallet1)
        assert len(wallet1_data["tags"]) == 2

    def test_batch_get_wallet_tags(self, test_client: TestClient, test_db: str):
        """Test getting tags for multiple wallets in one request"""
        wallets = ["DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK", "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku"]

        # Add tags
        test_client.post(f"/wallets/{wallets[0]}/tags", json={"tag": "whale"})
        test_client.post(f"/wallets/{wallets[1]}/tags", json={"tag": "degen"})

        # Batch get
        payload = {"addresses": wallets}
        response = test_client.post("/wallets/batch-tags", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert wallets[0] in data
        assert wallets[1] in data
