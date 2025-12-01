"""
Ingest Pipeline Configuration

Centralized configuration for DexScreener API and Tier-0/1 ingestion parameters.
Separates infrastructure config from user-adjustable settings.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class DexScreenerConfig:
    """Configuration for DexScreener API integration"""

    # API endpoints
    base_url: str = "https://api.dexscreener.com"
    token_pairs_endpoint: str = "/token-pairs/v1/solana/{address}"
    latest_profiles_endpoint: str = "/token-profiles/latest/v1"
    latest_boosts_endpoint: str = "/token-boosts/latest/v1"
    search_endpoint: str = "/latest/dex/search"

    # Rate limiting
    rate_limit_requests_per_minute: int = 60
    min_request_interval_seconds: float = 1.0
    rate_limit_backoff_seconds: int = 60
    request_timeout_seconds: int = 15

    # Default chain filter
    default_chain: str = "solana"

    # Tier-0 ingestion defaults (can be overridden by ingest settings)
    default_max_tokens_per_run: int = 50
    default_min_mc: float = 10000
    default_min_volume: float = 5000
    default_min_liquidity: float = 5000
    default_max_age_hours: float = 48

    # Discovery sources to query
    discovery_sources: List[str] = None

    def __post_init__(self):
        if self.discovery_sources is None:
            self.discovery_sources = ["profiles", "boosts"]


# Module-level singleton instance
DEXSCREENER_CONFIG = DexScreenerConfig()


def get_tier0_defaults() -> dict:
    """
    Get default Tier-0 ingestion parameters.

    Returns:
        Dictionary of default filter thresholds and limits
    """
    return {
        "max_tokens": DEXSCREENER_CONFIG.default_max_tokens_per_run,
        "mc_min": DEXSCREENER_CONFIG.default_min_mc,
        "volume_min": DEXSCREENER_CONFIG.default_min_volume,
        "liquidity_min": DEXSCREENER_CONFIG.default_min_liquidity,
        "age_max_hours": DEXSCREENER_CONFIG.default_max_age_hours,
    }
