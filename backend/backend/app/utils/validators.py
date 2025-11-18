"""
Validation utilities for Gun Del Sol

Provides common validation functions used across the application
"""

from datetime import datetime
from typing import Optional


def is_valid_solana_address(address: str) -> bool:
    """
    Basic Solana address validation

    Args:
        address: String to validate as Solana address

    Returns:
        True if valid, False otherwise
    """
    if not address or not isinstance(address, str):
        return False
    if len(address) < 32 or len(address) > 44:
        return False
    # Base58 characters only (no 0, O, I, l)
    base58 = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
    return all(ch in base58 for ch in address)


def format_timestamp(dt: Optional[datetime]) -> Optional[str]:
    """
    Format datetime to ISO string

    Args:
        dt: Datetime object to format

    Returns:
        ISO formatted string or None
    """
    if dt is None:
        return None
    return dt.isoformat()


def sanitize_address_for_logging(address: str) -> str:
    """
    Sanitize address for logging (show first 4 and last 4 characters)

    Args:
        address: Full address string

    Returns:
        Sanitized address like "AbC1...Xy89"
    """
    if len(address) <= 8:
        return "****"
    return f"{address[:4]}...{address[-4:]}"
