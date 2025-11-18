"""
Tests for validation utilities

Tests Solana address validation and other utility functions
"""

from datetime import datetime

import pytest

from app.utils.validators import format_timestamp, is_valid_solana_address, sanitize_address_for_logging


@pytest.mark.unit
class TestSolanaAddressValidation:
    """Test Solana address validation"""

    def test_valid_solana_addresses(self):
        """Test validation of valid Solana addresses"""
        valid_addresses = [
            "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK",
            "7xLk17EQQ5KLDLDe44wCmupJKJjTGd8hs3eSVVhCx6ku",
            "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
        ]

        for addr in valid_addresses:
            assert is_valid_solana_address(addr) is True

    def test_invalid_solana_addresses(self):
        """Test validation of invalid Solana addresses"""
        invalid_addresses = [
            "",  # Empty
            None,  # None
            "invalid",  # Too short
            "0123456789" * 10,  # Contains invalid characters (0)
            "I" * 44,  # Contains invalid character (I)
            "O" * 44,  # Contains invalid character (O)
            "l" * 44,  # Contains invalid character (l)
            "a" * 100,  # Too long
        ]

        for addr in invalid_addresses:
            assert is_valid_solana_address(addr) is False

    def test_address_length_validation(self):
        """Test address length requirements"""
        # Too short (< 32)
        assert is_valid_solana_address("a" * 31) is False

        # Minimum valid length (32)
        assert is_valid_solana_address("a" * 32) is True

        # Maximum valid length (44)
        assert is_valid_solana_address("a" * 44) is True

        # Too long (> 44)
        assert is_valid_solana_address("a" * 45) is False

    def test_base58_character_validation(self):
        """Test that only Base58 characters are allowed"""
        # Valid Base58 characters
        valid = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        assert is_valid_solana_address(valid[:40]) is True

        # Invalid characters (0, O, I, l)
        invalid_chars = ["0", "O", "I", "l"]
        for char in invalid_chars:
            addr = "a" * 39 + char  # 40 chars with one invalid
            assert is_valid_solana_address(addr) is False


@pytest.mark.unit
class TestTimestampFormatting:
    """Test timestamp formatting utilities"""

    def test_format_timestamp_with_datetime(self):
        """Test formatting a datetime object"""
        dt = datetime(2024, 1, 15, 10, 30, 45)
        result = format_timestamp(dt)
        assert result is not None
        assert "2024-01-15" in result
        assert "10:30:45" in result

    def test_format_timestamp_with_none(self):
        """Test formatting None returns None"""
        result = format_timestamp(None)
        assert result is None


@pytest.mark.unit
class TestAddressSanitization:
    """Test address sanitization for logging"""

    def test_sanitize_normal_address(self):
        """Test sanitizing a normal length address"""
        addr = "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"
        result = sanitize_address_for_logging(addr)

        assert result.startswith("DYw8")
        assert result.endswith("NSKK")
        assert "..." in result
        assert len(result) < len(addr)

    def test_sanitize_short_address(self):
        """Test sanitizing a short address"""
        addr = "short"
        result = sanitize_address_for_logging(addr)
        assert result == "****"

    def test_sanitize_exactly_8_chars(self):
        """Test sanitizing address that is exactly 8 characters"""
        addr = "12345678"
        result = sanitize_address_for_logging(addr)
        assert result == "****"

    def test_sanitize_9_chars(self):
        """Test sanitizing address that is 9 characters (minimum for display)"""
        addr = "123456789"
        result = sanitize_address_for_logging(addr)
        assert result.startswith("1234")
        assert result.endswith("6789")
