"""
Tests for watchlist router

Tests address registration, listing, updating, and deletion
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestAddressRegistration:
    """Test address registration endpoints"""

    def test_register_valid_address(self, test_client: TestClient, sample_wallet_address: str):
        """Test registering a valid Solana address"""
        payload = {"address": sample_wallet_address, "note": "Test wallet"}

        response = test_client.post("/register", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert data["address"] == sample_wallet_address
        assert data["threshold"] == 100
        assert "total_monitored" in data

    def test_register_duplicate_address(self, test_client: TestClient, sample_wallet_address: str):
        """Test registering the same address twice"""
        payload = {"address": sample_wallet_address}

        # First registration
        response = test_client.post("/register", json=payload)
        assert response.status_code == 200

        # Second registration (duplicate)
        response = test_client.post("/register", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "already_registered"
        assert data["address"] == sample_wallet_address

    def test_register_invalid_address(self, test_client: TestClient):
        """Test registering an invalid address"""
        payload = {"address": "invalid_address"}

        response = test_client.post("/register", json=payload)
        assert response.status_code == 422  # FastAPI validation error
        # Check that the response contains validation error information
        assert "detail" in response.json()

    def test_register_with_note(self, test_client: TestClient, sample_wallet_address: str):
        """Test registering address with a note"""
        payload = {"address": sample_wallet_address, "note": "Important whale wallet"}

        response = test_client.post("/register", json=payload)
        assert response.status_code == 200

        # Verify note was saved
        response = test_client.get(f"/address/{sample_wallet_address}")
        data = response.json()
        assert data["note"] == "Important whale wallet"


@pytest.mark.unit
class TestAddressListing:
    """Test address listing endpoints"""

    def test_list_empty_addresses(self, test_client: TestClient):
        """Test listing addresses when none are registered"""
        response = test_client.get("/addresses")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0
        assert data["addresses"] == []

    def test_list_addresses(self, test_client: TestClient):
        """Test listing registered addresses"""
        # Register multiple addresses
        addresses = ["DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK", "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku"]

        for addr in addresses:
            test_client.post("/register", json={"address": addr})

        # List addresses
        response = test_client.get("/addresses")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 2
        assert len(data["addresses"]) == 2

    def test_get_specific_address(self, test_client: TestClient, sample_wallet_address: str):
        """Test getting details of a specific address"""
        # Register address
        test_client.post("/register", json={"address": sample_wallet_address, "note": "Test note"})

        # Get address details
        response = test_client.get(f"/address/{sample_wallet_address}")
        assert response.status_code == 200

        data = response.json()
        assert data["address"] == sample_wallet_address
        assert data["note"] == "Test note"
        assert "registered_at" in data
        assert "threshold" in data

    def test_get_nonexistent_address(self, test_client: TestClient):
        """Test getting details of address that doesn't exist"""
        response = test_client.get("/address/NonExistentAddress123456789012345678901234")
        assert response.status_code == 404


@pytest.mark.unit
class TestAddressUpdate:
    """Test address update endpoints"""

    def test_update_address_note(self, test_client: TestClient, sample_wallet_address: str):
        """Test updating an address note"""
        # Register address
        test_client.post("/register", json={"address": sample_wallet_address})

        # Update note
        payload = {"note": "Updated note"}
        response = test_client.put(f"/address/{sample_wallet_address}/note", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert data["note"] == "Updated note"

        # Verify update
        response = test_client.get(f"/address/{sample_wallet_address}")
        assert response.json()["note"] == "Updated note"

    def test_clear_address_note(self, test_client: TestClient, sample_wallet_address: str):
        """Test clearing an address note"""
        # Register address with note
        test_client.post("/register", json={"address": sample_wallet_address, "note": "Original note"})

        # Clear note
        payload = {"note": None}
        response = test_client.put(f"/address/{sample_wallet_address}/note", json=payload)
        assert response.status_code == 200

        # Verify cleared
        response = test_client.get(f"/address/{sample_wallet_address}")
        assert response.json()["note"] is None

    def test_update_note_for_nonexistent_address(self, test_client: TestClient):
        """Test updating note for address that doesn't exist"""
        payload = {"note": "Test"}
        response = test_client.put("/address/NonExistent123456789012345678901234567/note", json=payload)
        assert response.status_code == 404


@pytest.mark.unit
class TestAddressDeletion:
    """Test address deletion endpoints"""

    def test_delete_address(self, test_client: TestClient, sample_wallet_address: str):
        """Test deleting a registered address"""
        # Register address
        test_client.post("/register", json={"address": sample_wallet_address})

        # Delete address
        response = test_client.delete(f"/address/{sample_wallet_address}")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert data["address"] == sample_wallet_address

        # Verify deletion
        response = test_client.get(f"/address/{sample_wallet_address}")
        assert response.status_code == 404

    def test_delete_nonexistent_address(self, test_client: TestClient):
        """Test deleting an address that doesn't exist"""
        response = test_client.delete("/address/NonExistent123456789012345678901234567")
        assert response.status_code == 404


@pytest.mark.unit
class TestBulkOperations:
    """Test bulk address operations"""

    def test_import_addresses(self, test_client: TestClient):
        """Test importing multiple addresses at once"""
        payload = {
            "addresses": [
                {"address": "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK", "note": "Wallet 1"},
                {"address": "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku", "note": "Wallet 2"},
            ]
        }

        response = test_client.post("/import", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert data["added"] == 2
        assert data["skipped"] == 0
        assert data["total"] >= 2

    def test_import_with_duplicates(self, test_client: TestClient, sample_wallet_address: str):
        """Test importing addresses with some duplicates"""
        # Register one address first
        test_client.post("/register", json={"address": sample_wallet_address})

        # Import including the duplicate
        payload = {
            "addresses": [
                {"address": sample_wallet_address},  # Duplicate
                {"address": "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku"},  # New
            ]
        }

        response = test_client.post("/import", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["added"] == 1
        assert data["skipped"] == 1

    def test_clear_all_addresses(self, test_client: TestClient):
        """Test clearing all monitored addresses"""
        # Register some addresses
        addresses = ["DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK", "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku"]
        for addr in addresses:
            test_client.post("/register", json={"address": addr})

        # Clear all
        response = test_client.post("/clear")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert data["total_monitored"] == 0

        # Verify cleared
        response = test_client.get("/addresses")
        assert response.json()["total"] == 0
