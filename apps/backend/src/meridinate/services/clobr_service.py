"""
CLOBr Service — Token liquidity intelligence via CLOBr.io API.

Provides liquidity scores (0-100) and market depth data (support/resistance levels)
for Solana tokens by querying CLOBr's aggregated DEX depth data. Runs as part of
the MC Tracker cycle to enrich tokens that have been alive long enough to have
DLMM liquidity.

Rate limit: 12 req/min, 100K calls/month on Premium.
"""

import time
from typing import Any, Dict, List, Optional

import requests

from meridinate.observability import log_error, log_info

CLOBR_BASE_URL = "https://clobr.io/api/v1"

# Rate limit: 12 requests per minute = 1 request per 5 seconds
MIN_REQUEST_INTERVAL = 5.0


class ClobrService:
    """CLOBr API client with rate limiting and response caching."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers["x-api-key"] = api_key
        self._last_request_time: float = 0
        self._score_cache: Dict[str, tuple] = {}  # address -> (result, timestamp)
        self._depth_cache: Dict[str, tuple] = {}  # address -> (result, timestamp)
        self._score_cache_ttl = 300  # 5 minute cache for scores
        self._depth_cache_ttl = 600  # 10 minute cache for depth (less volatile)
        self._calls_today = 0

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _request(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make a rate-limited request to CLOBr API."""
        self._rate_limit()
        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 429:
                log_info("[CLOBr] Rate limit hit, backing off")
                return None
            if response.status_code == 401:
                log_error("[CLOBr] Invalid API key")
                return None
            if not response.ok:
                return None
            self._calls_today += 1
            return response.json()
        except requests.exceptions.Timeout:
            log_error(f"[CLOBr] Timeout: {url}")
            return None
        except Exception as e:
            log_error(f"[CLOBr] Error: {e}")
            return None

    def get_score(self, token_address: str) -> Optional[Dict[str, Any]]:
        """
        Get CLOBr score for a single token.

        Returns:
            Dict with clobr_score (0-100), score_msg, price, status
            or None if unavailable/error
        """
        if token_address in self._score_cache:
            cached, cached_at = self._score_cache[token_address]
            if time.time() - cached_at < self._score_cache_ttl:
                return cached

        data = self._request(f"{CLOBR_BASE_URL}/score/{token_address}")
        if not data:
            return None

        raw_score = data.get("clobr_score")
        result = {
            "clobr_score": round(float(raw_score)) if raw_score is not None else None,
            "score_msg": data.get("score_msg"),
            "price": data.get("clobr_current_price"),
            "status": data.get("status"),
        }

        if data.get("status") == "available" and data.get("clobr_score") is not None:
            self._score_cache[token_address] = (result, time.time())

        return result

    def get_market_depth(self, token_address: str, low_pct: float = -0.2, high_pct: float = 0.2) -> Optional[Dict[str, Any]]:
        """
        Get market depth (support/resistance) for a token.

        Args:
            token_address: Token mint address
            low_pct: Lower price range (default -20% from current)
            high_pct: Upper price range (default +20% from current)

        Returns:
            Dict with support_usd, resistance_usd, sr_ratio, depth_levels, price
            or None if unavailable
        """
        cache_key = token_address
        if cache_key in self._depth_cache:
            cached, cached_at = self._depth_cache[cache_key]
            if time.time() - cached_at < self._depth_cache_ttl:
                return cached

        data = self._request(
            f"{CLOBR_BASE_URL}/market-depth",
            params={
                "token_address": token_address,
                "exchange_type": "DEX",
                "currency": "USD",
                "low_pct_change": low_pct,
                "high_pct_change": high_pct,
            },
        )
        if not data:
            return None

        depth_levels: List[dict] = data.get("depth_data") or []
        price = data.get("price")

        # Compute total support (below price) and resistance (above price)
        total_support = 0.0
        total_resistance = 0.0
        for level in depth_levels:
            support = level.get("support") or 0
            resistance = level.get("resistance") or 0
            total_support += support
            total_resistance += resistance

        sr_ratio = round(total_support / total_resistance, 2) if total_resistance > 0 else None

        result = {
            "support_usd": round(total_support, 2),
            "resistance_usd": round(total_resistance, 2),
            "sr_ratio": sr_ratio,
            "price": price,
            "clobr_score": data.get("clobr_score"),
            "score_msg": data.get("score_msg"),
            "depth_levels_count": len(depth_levels),
        }

        self._depth_cache[cache_key] = (result, time.time())
        return result

    def enrich_token(self, token_address: str, has_positions: bool = False) -> Optional[Dict[str, Any]]:
        """
        Full CLOBr enrichment for a token. Gets score, and optionally market depth
        for tokens with active positions.

        Returns:
            Dict with all CLOBr data merged, or None if token not on CLOBr
        """
        score_data = self.get_score(token_address)
        if not score_data or score_data.get("status") != "available":
            return None

        result = {
            "clobr_score": score_data.get("clobr_score"),
            "score_msg": score_data.get("score_msg"),
        }

        # Only fetch depth for position-tracked tokens (saves API calls)
        if has_positions:
            depth_data = self.get_market_depth(token_address)
            if depth_data:
                result["support_usd"] = depth_data["support_usd"]
                result["resistance_usd"] = depth_data["resistance_usd"]
                result["sr_ratio"] = depth_data["sr_ratio"]

        return result

    @property
    def calls_today(self) -> int:
        return self._calls_today

    def reset_daily_counter(self):
        self._calls_today = 0


# Singleton
_service: Optional[ClobrService] = None


def get_clobr_service() -> Optional[ClobrService]:
    """Get CLOBr service singleton. Returns None if no API key configured."""
    global _service
    if _service is not None:
        return _service

    from meridinate.settings import CLOBR_API_KEY
    if not CLOBR_API_KEY:
        return None

    _service = ClobrService(CLOBR_API_KEY)
    return _service
