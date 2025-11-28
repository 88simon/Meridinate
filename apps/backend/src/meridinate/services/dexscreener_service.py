"""
DexScreener Service for Token Discovery

Provides functions to fetch new/migrated tokens from DexScreener API.
Used by the Tier-0 ingestion pipeline for free token discovery.

API Reference:
- Rate limits: 60 requests/minute per IP (no API key required)
- Token pairs: https://api.dexscreener.com/token-pairs/v1/solana/{address}
- Latest profiles: https://api.dexscreener.com/token-profiles/latest/v1
- Search: https://api.dexscreener.com/latest/dex/search?q={query}
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import time

import requests

from meridinate.observability import log_error, log_info


class DexScreenerService:
    """Service for fetching token data from DexScreener API"""

    BASE_URL = "https://api.dexscreener.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "Meridinate/1.0",
        })
        self._last_request_time = 0
        self._min_request_interval = 1.0  # 1 second between requests to stay under rate limit

    def _rate_limited_request(self, url: str, timeout: int = 15) -> Optional[requests.Response]:
        """Make a rate-limited request to DexScreener API"""
        # Enforce minimum interval between requests
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)

        try:
            response = self.session.get(url, timeout=timeout)
            self._last_request_time = time.time()

            if response.status_code == 429:
                log_info("[DexScreener] Rate limit hit (429), backing off 60s")
                time.sleep(60)
                return None

            response.raise_for_status()
            return response

        except requests.RequestException as e:
            log_error(f"[DexScreener] Request failed: {e}")
            return None

    def get_latest_token_profiles(self, chain: str = "solana") -> List[Dict[str, Any]]:
        """
        Fetch latest token profiles from DexScreener.

        Returns tokens that have recently created profiles on DexScreener.
        This is useful for discovering newly listed/migrated tokens.

        Args:
            chain: Blockchain to filter for (default: solana)

        Returns:
            List of token profile dictionaries
        """
        url = f"{self.BASE_URL}/token-profiles/latest/v1"
        response = self._rate_limited_request(url)

        if not response:
            return []

        try:
            data = response.json()
            # Filter for Solana tokens
            solana_tokens = [
                t for t in data
                if t.get("chainId") == chain
            ]
            log_info(f"[DexScreener] Fetched {len(solana_tokens)} {chain} token profiles")
            return solana_tokens
        except Exception as e:
            log_error(f"[DexScreener] Failed to parse profiles response: {e}")
            return []

    def get_latest_boosted_tokens(self, chain: str = "solana") -> List[Dict[str, Any]]:
        """
        Fetch latest boosted tokens from DexScreener.

        Returns tokens that have been recently boosted (paid promotion).
        These are often new tokens trying to gain visibility.

        Args:
            chain: Blockchain to filter for (default: solana)

        Returns:
            List of boosted token dictionaries
        """
        url = f"{self.BASE_URL}/token-boosts/latest/v1"
        response = self._rate_limited_request(url)

        if not response:
            return []

        try:
            data = response.json()
            # Filter for Solana tokens
            solana_tokens = [
                t for t in data
                if t.get("chainId") == chain
            ]
            log_info(f"[DexScreener] Fetched {len(solana_tokens)} {chain} boosted tokens")
            return solana_tokens
        except Exception as e:
            log_error(f"[DexScreener] Failed to parse boosted response: {e}")
            return []

    def search_tokens(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for tokens on DexScreener.

        Args:
            query: Search query (e.g., token name, symbol, or address)

        Returns:
            List of matching pair dictionaries
        """
        url = f"{self.BASE_URL}/latest/dex/search?q={query}"
        response = self._rate_limited_request(url)

        if not response:
            return []

        try:
            data = response.json()
            pairs = data.get("pairs", [])
            # Filter for Solana pairs
            solana_pairs = [
                p for p in pairs
                if p.get("chainId") == "solana"
            ]
            return solana_pairs
        except Exception as e:
            log_error(f"[DexScreener] Failed to parse search response: {e}")
            return []

    def get_token_pairs(self, token_address: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get all trading pairs for a specific token.

        Args:
            token_address: Solana token mint address

        Returns:
            List of pair dictionaries, or None if not found
        """
        url = f"{self.BASE_URL}/token-pairs/v1/solana/{token_address}"
        response = self._rate_limited_request(url)

        if not response:
            return None

        try:
            data = response.json()
            if isinstance(data, list):
                return data
            return None
        except Exception as e:
            log_error(f"[DexScreener] Failed to parse pairs response: {e}")
            return None

    def get_token_snapshot(self, token_address: str) -> Optional[Dict[str, Any]]:
        """
        Get a snapshot of token metrics (market cap, volume, liquidity, age).

        Args:
            token_address: Solana token mint address

        Returns:
            Dictionary with token metrics, or None if not found
        """
        pairs = self.get_token_pairs(token_address)

        if not pairs or len(pairs) == 0:
            return None

        # Use the first (main) pair for metrics
        pair = pairs[0]

        # Calculate age from pairCreatedAt
        age_hours = None
        created_at = pair.get("pairCreatedAt")
        if created_at:
            try:
                # pairCreatedAt is Unix timestamp in milliseconds
                created_time = datetime.fromtimestamp(created_at / 1000)
                age_hours = (datetime.now() - created_time).total_seconds() / 3600
            except Exception:
                pass

        return {
            "token_address": pair.get("baseToken", {}).get("address"),
            "token_name": pair.get("baseToken", {}).get("name"),
            "token_symbol": pair.get("baseToken", {}).get("symbol"),
            "market_cap_usd": pair.get("marketCap"),
            "volume_24h_usd": pair.get("volume", {}).get("h24"),
            "liquidity_usd": pair.get("liquidity", {}).get("usd"),
            "price_usd": pair.get("priceUsd"),
            "pair_address": pair.get("pairAddress"),
            "dex_id": pair.get("dexId"),
            "age_hours": age_hours,
            "created_at": created_at,
        }

    def fetch_recent_migrated_tokens(
        self,
        max_tokens: int = 50,
        min_mc: float = 0,
        min_volume: float = 0,
        min_liquidity: float = 0,
        max_age_hours: float = 48,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Fetch recently migrated/listed tokens from DexScreener.

        Combines multiple sources (profiles, boosts, search) to find new tokens.
        Filters by market cap, volume, liquidity, and age thresholds.

        Args:
            max_tokens: Maximum number of tokens to return
            min_mc: Minimum market cap in USD
            min_volume: Minimum 24h volume in USD
            min_liquidity: Minimum liquidity in USD
            max_age_hours: Maximum token age in hours

        Returns:
            Tuple of (list of token dictionaries, count of tokens fetched)
        """
        seen_addresses = set()
        tokens = []

        # Source 1: Latest token profiles
        profiles = self.get_latest_token_profiles("solana")
        for profile in profiles:
            address = profile.get("tokenAddress")
            if not address or address in seen_addresses:
                continue

            # Get full token snapshot
            snapshot = self.get_token_snapshot(address)
            if not snapshot:
                continue

            # Apply filters
            mc = snapshot.get("market_cap_usd") or 0
            vol = snapshot.get("volume_24h_usd") or 0
            liq = snapshot.get("liquidity_usd") or 0
            age = snapshot.get("age_hours")

            if mc < min_mc:
                continue
            if vol < min_volume:
                continue
            if liq < min_liquidity:
                continue
            if age is not None and age > max_age_hours:
                continue

            seen_addresses.add(address)
            tokens.append(snapshot)

            if len(tokens) >= max_tokens:
                break

        # Source 2: Latest boosted tokens (if not enough from profiles)
        if len(tokens) < max_tokens:
            boosts = self.get_latest_boosted_tokens("solana")
            for boost in boosts:
                address = boost.get("tokenAddress")
                if not address or address in seen_addresses:
                    continue

                snapshot = self.get_token_snapshot(address)
                if not snapshot:
                    continue

                # Apply filters
                mc = snapshot.get("market_cap_usd") or 0
                vol = snapshot.get("volume_24h_usd") or 0
                liq = snapshot.get("liquidity_usd") or 0
                age = snapshot.get("age_hours")

                if mc < min_mc:
                    continue
                if vol < min_volume:
                    continue
                if liq < min_liquidity:
                    continue
                if age is not None and age > max_age_hours:
                    continue

                seen_addresses.add(address)
                tokens.append(snapshot)

                if len(tokens) >= max_tokens:
                    break

        log_info(f"[DexScreener] Found {len(tokens)} tokens after filtering")
        return tokens, len(tokens)


# Module-level singleton
_dexscreener_service: Optional[DexScreenerService] = None


def get_dexscreener_service() -> DexScreenerService:
    """Get or create the DexScreener service singleton"""
    global _dexscreener_service
    if _dexscreener_service is None:
        _dexscreener_service = DexScreenerService()
    return _dexscreener_service
