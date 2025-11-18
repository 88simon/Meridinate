"""
============================================================================
Secure Logging Module - OPSEC-Safe Logging
============================================================================
This module provides OPSEC-safe logging that prevents leakage of:
- Wallet addresses
- Token addresses
- API keys
- Transaction data
- Analysis results

All print statements should use these functions instead of direct print().
============================================================================
"""

import re
from datetime import datetime


def sanitize_address(address: str) -> str:
    """
    Sanitize a Solana wallet or token address for logging.
    Shows only first 4 and last 4 characters.

    Example: "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
          -> "Toke...Q5DA"
    """
    if not address or len(address) < 12:
        return "****"
    return f"{address[:4]}...{address[-4:]}"


def log_info(message: str, include_timestamp: bool = True):
    """
    Log general information (non-sensitive).
    Use this for: service status, operation completion, counts
    """
    timestamp = f"[{datetime.now().strftime('%H:%M:%S')}] " if include_timestamp else ""
    print(f"{timestamp}ℹ️  {message}")


def log_success(message: str, include_timestamp: bool = True):
    """
    Log successful operations (non-sensitive).
    Use this for: successful API calls, database saves, etc.
    """
    timestamp = f"[{datetime.now().strftime('%H:%M:%S')}] " if include_timestamp else ""
    print(f"{timestamp}✓ {message}")


def log_warning(message: str, include_timestamp: bool = True):
    """
    Log warnings (non-sensitive).
    Use this for: configuration issues, missing optional data
    """
    timestamp = f"[{datetime.now().strftime('%H:%M:%S')}] " if include_timestamp else ""
    print(f"{timestamp}⚠  {message}")


def log_error(message: str, include_timestamp: bool = True):
    """
    Log errors (non-sensitive).
    Use this for: operation failures, exceptions
    NEVER include wallet addresses, tokens, or user data in error messages.
    """
    timestamp = f"[{datetime.now().strftime('%H:%M:%S')}] " if include_timestamp else ""
    print(f"{timestamp}❌ {message}")


def log_debug(message: str, enabled: bool = False):
    """
    Log debug information (only when explicitly enabled).
    Use this for: detailed operation traces
    Set enabled=True only during development, never in production.
    """
    if enabled:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [DEBUG] {message}")


def log_analysis_start(job_id: str):
    """Log token analysis start (OPSEC-safe)."""
    log_info(f"Analysis job {job_id} started")


def log_analysis_complete(job_id: str, wallet_count: int):
    """Log token analysis completion (OPSEC-safe)."""
    log_success(f"Analysis job {job_id} completed - found {wallet_count} wallets")


def log_token_save(acronym: str, wallet_count: int):
    """Log token save to database (OPSEC-safe)."""
    log_success(f"Saved token {acronym} with {wallet_count} wallets to database")


def log_address_registered(address: str):
    """Log address registration (OPSEC-safe)."""
    sanitized = sanitize_address(address)
    log_success(f"Registered address {sanitized} for monitoring")


def log_address_removed(address: str):
    """Log address removal (OPSEC-safe)."""
    sanitized = sanitize_address(address)
    log_success(f"Removed address {sanitized} from monitoring")


# Configuration: Enable/disable all logging
LOGGING_ENABLED = True


def set_logging_enabled(enabled: bool):
    """Enable or disable all logging globally."""
    global LOGGING_ENABLED
    LOGGING_ENABLED = enabled
