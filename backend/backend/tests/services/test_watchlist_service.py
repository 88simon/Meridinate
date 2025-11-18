"""
Tests for watchlist service

Tests watchlist business logic and data persistence
"""

import json
import os
import tempfile

import pytest

from app import state
from app.services.watchlist_service import WatchlistService, get_watchlist_service


@pytest.mark.unit
class TestWatchlistService:
    """Test watchlist service functionality"""

    @pytest.fixture
    def temp_data_file(self):
        """Create a temporary data file for testing"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = f.name
            json.dump({}, f)

        yield temp_file

        # Cleanup
        if os.path.exists(temp_file):
            os.unlink(temp_file)

    @pytest.fixture
    def watchlist_service(self, temp_data_file, monkeypatch):
        """Create a watchlist service with temporary data file"""
        from app import settings

        monkeypatch.setattr(settings, "DATA_FILE", temp_data_file)

        # Clear state
        state.monitored_addresses.clear()

        service = WatchlistService()
        return service

    def test_register_address(self, watchlist_service):
        """Test registering a new address"""
        address = "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"
        result = watchlist_service.register_address(address, note="Test wallet")

        assert result["status"] == "success"
        assert result["address"] == address
        assert result["total_monitored"] == 1

    def test_register_duplicate_address(self, watchlist_service):
        """Test registering the same address twice"""
        address = "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"

        # First registration
        watchlist_service.register_address(address)

        # Second registration
        result = watchlist_service.register_address(address)
        assert result["status"] == "already_registered"

    def test_get_address(self, watchlist_service):
        """Test getting a specific address"""
        address = "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"
        watchlist_service.register_address(address, note="Important wallet")

        result = watchlist_service.get_address(address)
        assert result is not None
        assert result["address"] == address
        assert result["note"] == "Important wallet"

    def test_get_nonexistent_address(self, watchlist_service):
        """Test getting address that doesn't exist"""
        result = watchlist_service.get_address("NonExistent123456789012345678901234")
        assert result is None

    def test_list_addresses(self, watchlist_service):
        """Test listing all addresses"""
        addresses = ["DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK", "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku"]

        for addr in addresses:
            watchlist_service.register_address(addr)

        result = watchlist_service.list_addresses()
        assert result["total"] == 2
        assert len(result["addresses"]) == 2

    def test_unregister_address(self, watchlist_service):
        """Test removing an address"""
        address = "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"
        watchlist_service.register_address(address)

        result = watchlist_service.unregister_address(address)
        assert result["status"] == "success"

        # Verify removal
        assert watchlist_service.get_address(address) is None

    def test_unregister_nonexistent_address(self, watchlist_service):
        """Test removing address that doesn't exist"""
        with pytest.raises(ValueError):
            watchlist_service.unregister_address("NonExistent123456789012345678901234")

    def test_update_note(self, watchlist_service):
        """Test updating address note"""
        address = "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"
        watchlist_service.register_address(address, note="Original note")

        result = watchlist_service.update_note(address, "Updated note")
        assert result["status"] == "success"
        assert result["note"] == "Updated note"

        # Verify update
        addr_data = watchlist_service.get_address(address)
        assert addr_data["note"] == "Updated note"

    def test_update_note_for_nonexistent_address(self, watchlist_service):
        """Test updating note for address that doesn't exist"""
        with pytest.raises(ValueError):
            watchlist_service.update_note("NonExistent123456789012345678901234", "Test")

    def test_import_addresses(self, watchlist_service):
        """Test importing multiple addresses"""
        entries = [
            {"address": "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK", "note": "Wallet 1"},
            {"address": "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku", "note": "Wallet 2"},
        ]

        result = watchlist_service.import_addresses(entries)
        assert result["status"] == "success"
        assert result["added"] == 2
        assert result["skipped"] == 0

    def test_import_with_duplicates(self, watchlist_service):
        """Test importing addresses with duplicates"""
        # Register one address first
        watchlist_service.register_address("DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK")

        # Import including duplicate
        entries = [
            {"address": "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"},
            {"address": "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku"},
        ]

        result = watchlist_service.import_addresses(entries)
        assert result["added"] == 1
        assert result["skipped"] == 1

    def test_clear_all(self, watchlist_service):
        """Test clearing all addresses"""
        # Add some addresses
        addresses = ["DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK", "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku"]
        for addr in addresses:
            watchlist_service.register_address(addr)

        # Clear all
        result = watchlist_service.clear_all()
        assert result["status"] == "success"
        assert result["total_monitored"] == 0

        # Verify cleared
        list_result = watchlist_service.list_addresses()
        assert list_result["total"] == 0

    def test_persistence(self, watchlist_service, temp_data_file):
        """Test that data persists to file"""
        address = "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"
        watchlist_service.register_address(address, note="Persistent wallet")

        # Verify data was saved to file
        with open(temp_data_file, "r") as f:
            data = json.load(f)

        assert address in data
        assert data[address]["note"] == "Persistent wallet"

    def test_get_watchlist_service_singleton(self):
        """Test that get_watchlist_service returns singleton"""
        service1 = get_watchlist_service()
        service2 = get_watchlist_service()

        assert service1 is service2
