"""
============================================================================
Debug Configuration - Centralized Debug Logging Control
============================================================================
This module provides a single killswitch to control ALL debug logging
across the entire application (Python and JavaScript).

PRODUCTION MODE (Default):
    DEBUG_MODE = False
    - No sensitive data logged to terminal
    - No sensitive data logged to browser console
    - Safe for screen sharing and recording

DEBUG MODE (Troubleshooting):
    DEBUG_MODE = True
    - Full logging enabled everywhere
    - Wallet addresses, token addresses, transaction data visible
    - Use ONLY when debugging locally

============================================================================
"""

# ============================================================================
# SINGLE KILLSWITCH - Change this ONE value to control ALL logging
# ============================================================================
DEBUG_MODE = False  # Set to True to enable ALL debug logging (OPSEC WARNING)
# ============================================================================


def is_debug_enabled() -> bool:
    """Check if debug mode is enabled"""
    return DEBUG_MODE


def get_debug_js_flag() -> str:
    """Get JavaScript debug flag value as string"""
    return "true" if DEBUG_MODE else "false"
