"""
PumpFun API Service

Fetches token metadata from PumpFun's frontend API.
Provides: cashback status, true ATH, creator address, bonding curve data.
Free API — no credits needed.
"""

import requests
from typing import Optional, Dict, Any
from meridinate.observability import log_error


PUMPFUN_API_BASE = "https://frontend-api-v3.pump.fun"


def get_pumpfun_token_data(token_address: str) -> Optional[Dict[str, Any]]:
    """
    Fetch token data from PumpFun's API.

    Returns:
        Dict with: is_cashback_enabled, ath_market_cap, creator, complete (graduated), etc.
        None if token not found or not a PumpFun token.
    """
    try:
        response = requests.get(
            f"{PUMPFUN_API_BASE}/coins/{token_address}",
            timeout=5,
        )
        if response.status_code == 404:
            return None  # Not a PumpFun token
        response.raise_for_status()
        data = response.json()

        return {
            "is_cashback_enabled": data.get("is_cashback_enabled", False),
            "ath_market_cap": data.get("ath_market_cap"),
            "ath_market_cap_timestamp": data.get("ath_market_cap_timestamp"),
            "creator": data.get("creator"),
            "complete": data.get("complete", False),  # True = graduated from bonding curve
            "usd_market_cap": data.get("usd_market_cap"),
            "total_supply": data.get("total_supply"),
            "nsfw": data.get("nsfw", False),
            "is_banned": data.get("is_banned", False),
        }
    except Exception as e:
        log_error(f"[PumpFun] Error fetching {token_address[:12]}: {e}")
        return None
