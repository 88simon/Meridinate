"""
Helius API Integration for Solana Token Analysis
Provides functions to analyze tokens and extract early bidder data
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import base58
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import builtins

from meridinate.debug_config import is_debug_enabled
from meridinate.cache import ResponseCache

# ============================================================================
# OPSEC: PRODUCTION MODE - Disable Sensitive Logging
# ============================================================================
# Debug logging is controlled by debug_config.py - change DEBUG_MODE there
# ============================================================================


def safe_print(*args, **kwargs):
    """Only print if debug mode is enabled in debug_config.py"""
    if is_debug_enabled():
        builtins.print(*args, **kwargs)


# Replace built-in print with safe version
print = safe_print
# ============================================================================


class HeliusAPI:
    """Wrapper for Helius RPC and Enhanced API endpoints"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.rpc_url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
        self.enhanced_url = "https://api.helius.xyz/v0"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.api_credits_used = 0  # Track API credits used

        # SOL price caching to avoid excessive API calls
        self._sol_price_cache = None
        self._sol_price_cache_time = None
        self._sol_price_cache_duration = 300  # Cache for 5 minutes

        # Response cache for DexScreener and wallet balances
        # DexScreener: 5 minute TTL (market cap doesn't change that rapidly)
        # Wallet balances: 5 minute TTL (balance can be manually refreshed)
        self._dexscreener_cache = ResponseCache(ttl=300, name="dexscreener")
        self._wallet_balance_cache = ResponseCache(ttl=300, name="wallet_balance")

    def _get_sol_price_usd(self) -> float:
        """
        Get current SOL price in USD from CoinGecko API (free, no API key required).
        Uses caching to avoid excessive API calls (5-minute cache).

        Returns:
            Current SOL price in USD, or 100.0 as fallback if API fails
        """
        from datetime import datetime

        # Check if we have a valid cached price
        if self._sol_price_cache is not None and self._sol_price_cache_time is not None:
            time_elapsed = (datetime.now() - self._sol_price_cache_time).total_seconds()
            if time_elapsed < self._sol_price_cache_duration:
                return self._sol_price_cache

        # Fetch fresh price from CoinGecko
        try:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {"ids": "solana", "vs_currencies": "usd"}
            # Use persistent session for connection reuse
            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            sol_price = data.get("solana", {}).get("usd")
            if sol_price and sol_price > 0:
                # Update cache
                self._sol_price_cache = float(sol_price)
                self._sol_price_cache_time = datetime.now()
                print(f"[Helius] SOL price updated: ${sol_price:.2f} USD")
                return self._sol_price_cache

        except Exception as e:
            print(f"[Helius] Failed to fetch SOL price from CoinGecko: {str(e)}")

        # Fallback to a reasonable default if API fails
        fallback_price = 100.0
        print(f"[Helius] Using fallback SOL price: ${fallback_price:.2f} USD")
        return fallback_price

    def is_wallet_on_curve(self, wallet_address: str) -> bool:
        """
        Check if a wallet address is on-curve using Solana's PublicKey validation.
        On-curve addresses are valid ed25519 curve points that can sign transactions.
        """
        try:
            # Use base58 to decode and validate the address
            decoded = base58.b58decode(wallet_address)
            # Solana addresses are 32 bytes
            if len(decoded) != 32:
                return False
            # If it decodes properly and is 32 bytes, it's on-curve
            return True
        except Exception:
            return False

    def get_wallet_balance(self, wallet_address: str, force_refresh: bool = False) -> tuple[Optional[float], int]:
        """
        Get wallet balance in USD for a wallet address.

        Caching: 5 minute TTL to reduce API calls. Can be bypassed with force_refresh.

        Args:
            wallet_address: Solana wallet address
            force_refresh: If True, bypass cache and fetch fresh balance

        Returns:
            Tuple of (balance in USD, API credits used)
            Returns (None, 0) if the call fails
        """
        # Check cache first (unless force_refresh is True)
        cache_key = f"wallet_balance:{wallet_address}"
        if not force_refresh:
            cached_balance, _ = self._wallet_balance_cache.get(cache_key)
            if cached_balance is not None:
                print(f"[Helius] Cache hit for wallet {wallet_address}: ${cached_balance:,.2f} USD (0 credits)")
                return cached_balance, 0  # No API credits used for cached result

        try:
            result = self._rpc_call("getBalance", [wallet_address])
            # getBalance returns lamports (1 SOL = 1,000,000,000 lamports)
            if result and "value" in result:
                lamports = result["value"]
                sol_balance = lamports / 1_000_000_000

                # Get current SOL price from CoinGecko (cached for 5 minutes)
                sol_price_usd = self._get_sol_price_usd()
                usd_balance = sol_balance * sol_price_usd

                # Cache the result
                self._wallet_balance_cache.set(cache_key, usd_balance)

                # getBalance costs 1 credit per call
                return usd_balance, 1
            return None, 0
        except Exception as e:
            print(f"Error fetching wallet balance for {wallet_address}: {str(e)}")
            return None, 0

    def _rpc_call(self, method: str, params: list) -> dict:
        """Make a JSON-RPC call to Helius"""
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        try:
            response = self.session.post(self.rpc_url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            if "error" in result:
                raise Exception(f"RPC Error: {result['error']}")
            return result.get("result", {})
        except Exception as e:
            raise Exception(f"RPC call failed: {str(e)}")

    def _enhanced_call(self, endpoint: str, params: dict) -> dict:
        """Make a call to Helius Enhanced API"""
        url = f"{self.enhanced_url}/{endpoint}"
        params["api-key"] = self.api_key
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"Enhanced API call failed: {str(e)}")

    def get_token_metadata(self, mint_address: str) -> tuple[Optional[Dict], int]:
        """
        Get token metadata including name, symbol, market cap, etc.

        Returns:
            Tuple of (metadata dict, credits_used)
            metadata dict includes:
            - onChainMetadata: {metadata: {name, symbol}}
            - legacyMetadata: original metadata
            - market_cap_usd: calculated market capitalization (if available)
        """
        try:
            # Try the regular token metadata endpoint first
            result = self._enhanced_call("token-metadata", {"mintAccounts": mint_address})
            if result and result[0]:
                # Enhanced API token-metadata costs 1 credit
                return result[0], 1
        except Exception as e:
            print(f"Error fetching token metadata (standard): {str(e)}")

        # For pump.fun tokens, try DAS API (Digital Asset Standard)
        try:
            print("[Helius] Trying DAS API for token metadata...")
            payload = {
                "jsonrpc": "2.0",
                "id": "token-metadata",
                "method": "getAsset",
                "params": {
                    "id": mint_address,
                    "displayOptions": {"showUnverifiedCollections": True, "showCollectionMetadata": True},
                },
            }
            response = self.session.post(self.rpc_url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()

            if "result" in result and result["result"]:
                asset = result["result"]
                # Extract name and symbol from DAS response
                content = asset.get("content", {})
                metadata = content.get("metadata", {})

                token_name = metadata.get("name") or content.get("json_uri", "Unknown")
                token_symbol = metadata.get("symbol", "UNK")

                print(f"[Helius] DAS API found: {token_name} ({token_symbol})")

                # Extract market cap information if available
                market_cap_usd = None
                try:
                    token_info = asset.get("token_info", {})
                    if token_info:
                        # Get price per token (in USD) and supply
                        price_info = token_info.get("price_info")
                        supply = token_info.get("supply")
                        decimals = token_info.get("decimals", 0)

                        if price_info and supply is not None:
                            price_per_token = price_info.get("price_per_token")
                            if price_per_token is not None and price_per_token > 0:
                                # Adjust supply for decimals to get actual circulating supply
                                adjusted_supply = float(supply) / (10**decimals) if decimals > 0 else float(supply)
                                # Calculate market cap
                                market_cap_usd = price_per_token * adjusted_supply
                                print(
                                    f"[Helius] Market cap calculated: ${market_cap_usd:,.2f} USD (price: ${price_per_token}, supply: {adjusted_supply:,.0f})"
                                )
                except Exception as market_cap_error:
                    print(f"[Helius] Could not calculate market cap: {str(market_cap_error)}")

                # Format it similar to standard metadata response
                formatted = {
                    "onChainMetadata": {"metadata": {"name": token_name, "symbol": token_symbol}},
                    "legacyMetadata": metadata,
                    "market_cap_usd": market_cap_usd,
                }
                # DAS API getAsset costs 1 credit
                return formatted, 1
        except Exception as das_error:
            print(f"Error fetching token metadata (DAS): {str(das_error)}")

        return None, 0

    def get_market_cap_from_dexscreener(self, mint_address: str) -> Optional[float]:
        """
        Get market cap from DexScreener API (free, no API credits).

        DexScreener has excellent coverage of pump.fun and other DEX tokens.
        This is used as the primary source, with Helius as fallback.

        Rate Limits: 60 requests/minute per IP (no API key required)
        - HTTP 429 if rate limit exceeded (cooldown: 30-60 seconds)
        - Our sequential processing stays well within limits for typical use

        Caching: 5 minute TTL to reduce API calls and avoid rate limiting

        Args:
            mint_address: Token mint address

        Returns:
            Market cap in USD, or None if not available
        """
        # Check cache first
        cache_key = f"dexscreener_mc:{mint_address}"
        cached_value, _ = self._dexscreener_cache.get(cache_key)
        if cached_value is not None:
            print(f"[DexScreener] Cache hit for {mint_address}: ${cached_value:,.2f} USD")
            return cached_value

        try:
            url = f"https://api.dexscreener.com/token-pairs/v1/solana/{mint_address}"
            response = self.session.get(url, timeout=10)

            # Handle rate limiting specifically
            if response.status_code == 429:
                print("[DexScreener] Rate limit exceeded (429) - try again in ~1 minute")
                print("[DexScreener] Falling back to Helius for this request")
                return None

            response.raise_for_status()

            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                # DexScreener returns array of pairs, take the first one (usually the main pool)
                pair = data[0]
                market_cap = pair.get("marketCap")

                if market_cap is not None and market_cap > 0:
                    market_cap_float = float(market_cap)
                    print(f"[DexScreener] Market cap found: ${market_cap_float:,.2f} USD")
                    # Cache the result
                    self._dexscreener_cache.set(cache_key, market_cap_float)
                    return market_cap_float
                else:
                    print("[DexScreener] Market cap not available (null or zero)")
                    return None
            else:
                print("[DexScreener] No pairs found for this token")
                return None

        except Exception as e:
            # Don't print stack trace for rate limiting - it's expected
            if "429" not in str(e):
                print(f"[DexScreener] Error fetching market cap: {str(e)}")
            return None

    def get_market_cap_with_fallback(self, mint_address: str) -> tuple[Optional[float], int]:
        """
        Get market cap with DexScreener primary + Helius fallback.

        Strategy:
        1. Try DexScreener first (free, excellent pump.fun coverage)
        2. If DexScreener returns None, fall back to Helius DAS API

        Args:
            mint_address: Token mint address

        Returns:
            Tuple of (market_cap_usd, api_credits_used)
            - market_cap_usd: Market capitalization in USD, or None if unavailable
            - api_credits_used: Number of Helius API credits consumed (0 if only DexScreener used)
        """
        # Try DexScreener first (free, no credits)
        print(f"[MarketCap] Fetching market cap for {mint_address}...")
        market_cap = self.get_market_cap_from_dexscreener(mint_address)

        if market_cap is not None:
            print(f"[MarketCap] Using DexScreener data: ${market_cap:,.2f}")
            return market_cap, 0  # DexScreener is free, no credits used

        # Fall back to Helius if DexScreener didn't work
        print("[MarketCap] DexScreener unavailable, falling back to Helius DAS API...")
        token_info, credits = self.get_token_metadata(mint_address)

        if token_info:
            helius_market_cap = token_info.get("market_cap_usd")
            if helius_market_cap:
                print(f"[MarketCap] Using Helius data: ${helius_market_cap:,.2f} (used {credits} credits)")
                return helius_market_cap, credits
            else:
                print(f"[MarketCap] Helius also returned null (used {credits} credits)")
                return None, credits

        print("[MarketCap] No market cap data available from any source")
        return None, 0

    def get_token_creation_time(self, mint_address: str) -> tuple[Optional[int], int]:
        """
        Get the token creation timestamp by finding the first transaction.

        NOTE: This method is currently DISABLED because it's too expensive.
        It would require paginating through ALL transactions just to find the first one.

        Instead, we'll just return None and let the transaction fetching handle it naturally.

        Args:
            mint_address: Token mint address

        Returns:
            Tuple of (creation_timestamp in unix time, credits_used)
        """
        # DISABLED: This is too expensive - would need to paginate through potentially
        # tens of thousands of signatures just to find the first one
        print(f"[Helius] Skipping token creation time lookup (too expensive)")
        return None, 0

    def get_parsed_transactions(
        self,
        address: str,
        limit: int = 100,
        get_earliest: bool = False,
        token_creation_time: int = None,
        max_credits: int = 1000,
    ) -> tuple[List[Dict], int]:
        """
        Get parsed transaction history for an address.
        Returns transactions with decoded swap/transfer data.

        Args:
            address: Solana address to fetch transactions for
            limit: Maximum number of transactions to fetch
            get_earliest: If True, fetches earliest transactions from token creation.
                         If False, fetches most recent transactions (default)
            token_creation_time: Unix timestamp of token creation (optional, improves efficiency)

        Returns:
            Tuple of (List of transactions, API credits used)
        """
        try:
            if get_earliest:
                # Fetch earliest transactions using the new efficient method
                return self._get_earliest_transactions_new(address, limit, token_creation_time, max_credits)

            # Get transaction signatures first (most recent by default)
            # NOTE: getSignaturesForAddress costs 1 credit per call on Helius paid plans
            signatures = self._rpc_call("getSignaturesForAddress", [address, {"limit": limit}])
            signature_api_calls = 1  # 1 credit for the signature fetch

            if not signatures:
                return [], signature_api_calls

            sig_list = [sig["signature"] for sig in signatures[:limit]]
            print(f"[Helius] Fetching details for {len(sig_list)} transactions...")

            # Fetch transactions individually using RPC method
            # Each getTransaction call costs 1 credit
            all_transactions = []
            transaction_api_calls = 0

            for i, signature in enumerate(sig_list):
                if i % 50 == 0:  # Progress indicator every 50 transactions
                    print(f"[Helius] Progress: {i}/{len(sig_list)} transactions fetched...")

                try:
                    # Use getTransaction RPC method with maxSupportedTransactionVersion
                    tx_data = self._rpc_call(
                        "getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
                    )
                    transaction_api_calls += 1  # 1 credit per getTransaction call

                    if tx_data:
                        # Extract relevant transaction info
                        parsed_tx = self._parse_rpc_transaction(tx_data, signature)
                        if parsed_tx:
                            all_transactions.append(parsed_tx)

                except Exception as tx_error:
                    # Skip individual transaction errors
                    continue

            total_credits = signature_api_calls + transaction_api_calls
            print(f"[Helius] Total transactions retrieved: {len(all_transactions)}")
            print(
                f"[Helius] API credits used: {signature_api_calls} signature calls + {transaction_api_calls} transaction calls = {total_credits} total"
            )
            return all_transactions, total_credits

        except Exception as e:
            print(f"Error fetching parsed transactions: {str(e)}")
            return [], 0

    def _get_earliest_transactions_new(
        self, address: str, limit: int = 500, token_creation_time: int = None, max_credits: int = 1000
    ) -> tuple[List[Dict], int]:
        """
        Fetch earliest transactions for an address using Helius's getTransactionsForAddress.
        This is MUCH more efficient than the old method - uses timestamp filtering and ascending order.

        Args:
            address: Solana address to fetch transactions for
            limit: Maximum number of earliest transactions to return
            token_creation_time: Unix timestamp of token creation (optional)
            max_credits: Maximum API credits to spend (default: 1000)

        Returns:
            Tuple of (List of parsed transactions oldest first, API credits used)
        """
        print(f"[Helius] Fetching earliest transactions using getTransactionsForAddress (efficient method)...")
        print(f"[Helius] Credit limit: {max_credits} credits (max {max_credits // 100} API calls)")
        if token_creation_time:
            print(f"[Helius] Filtering from token creation time: {datetime.utcfromtimestamp(token_creation_time)}")

        all_transactions = []
        api_calls = 0
        pagination_token = None
        max_api_calls = max_credits // 100  # Each call costs 100 credits

        try:
            # getTransactionsForAddress costs 100 credits per call
            # Can fetch up to 100 transactions with full details per call
            # We'll need multiple calls if limit > 100
            # The max_api_calls (derived from max_credits) is the actual limiting factor
            remaining_limit = limit

            while remaining_limit > 0 and api_calls < max_api_calls:
                batch_limit = min(remaining_limit, 100)  # Max 100 per call with full details

                # Build request params
                params = [
                    address,
                    {
                        "transactionDetails": "full",  # Get full transaction details
                        "limit": batch_limit,
                        "sortOrder": "asc",  # Ascending = oldest first!
                    },
                ]

                # Add timestamp filter if we have token creation time
                if token_creation_time:
                    params[1]["filters"] = {
                        "blockTime": {"gte": token_creation_time}  # Greater than or equal to creation time
                    }

                # Add pagination token if we have one
                if pagination_token:
                    params[1]["paginationToken"] = pagination_token

                print(f"[Helius] Calling getTransactionsForAddress (batch limit: {batch_limit})...")
                print(f"[Helius] Request params: {params}")

                # Make the RPC call
                result = self._rpc_call("getTransactionsForAddress", params)
                api_calls += 1  # 100 credits per call

                print(f"[Helius] Raw result type: {type(result)}")
                print(f"[Helius] Raw result keys: {result.keys() if isinstance(result, dict) else 'N/A'}")

                if not result:
                    print(f"[Helius] Result is empty/None, breaking")
                    break

                # Extract transactions and pagination token
                # Note: getTransactionsForAddress returns 'data', not 'transactions'
                transactions = result.get("data", [])
                pagination_token = result.get("paginationToken")

                print(f"[Helius] Received {len(transactions)} transactions in this batch")
                print(f"[Helius] Pagination token: {pagination_token}")

                # Parse each transaction
                for tx_data in transactions:
                    try:
                        # tx_data is already the full transaction object
                        signature = tx_data.get("signature")
                        parsed_tx = self._parse_rpc_transaction(tx_data, signature)
                        if parsed_tx:
                            all_transactions.append(parsed_tx)
                    except Exception as parse_error:
                        continue

                remaining_limit -= len(transactions)

                # If no pagination token or no more transactions, we're done
                if not pagination_token or len(transactions) == 0:
                    break

                # If we got fewer than requested, we've reached the end
                if len(transactions) < batch_limit:
                    break

            total_credits = api_calls * 100  # Each call costs 100 credits
            print(f"[Helius] Total transactions retrieved: {len(all_transactions)}")
            print(f"[Helius] API credits used: {api_calls} calls × 100 credits = {total_credits} total")

            # Warn if we hit the credit limit
            if api_calls >= max_api_calls:
                print(f"[Helius] ⚠️  WARNING: Reached credit limit ({max_credits} credits)")
                print(f"[Helius] Analysis may be incomplete. Consider increasing maxCreditsPerAnalysis in settings.")

            return all_transactions, total_credits

        except Exception as e:
            print(f"[Helius] ERROR in getTransactionsForAddress: {str(e)}")
            import traceback

            print(f"[Helius] Traceback: {traceback.format_exc()}")
            # Fall back to old method if new method fails
            print(f"[Helius] Falling back to old pagination method...")
            return self._get_earliest_transactions_old(address, limit, token_creation_time)

    def _get_earliest_transactions_old(
        self, address: str, limit: int = 500, token_creation_time: int = None
    ) -> tuple[List[Dict], int]:
        """
        OLD METHOD: Fetch earliest transactions for an address via backward pagination.
        This is kept as a fallback but is MUCH less efficient than the new method.

        Args:
            address: Solana address to fetch transactions for
            limit: Maximum number of earliest transactions to return
            token_creation_time: Unix timestamp of token creation (optional)

        Returns:
            Tuple of (List of parsed transactions oldest first, API credits used)
        """
        print(f"[Helius] Fetching earliest transactions (OLD backward pagination method)...")
        if token_creation_time:
            print(f"[Helius] Starting from token creation time: {datetime.utcfromtimestamp(token_creation_time)}")

        all_signatures = []
        batch_size = 1000  # Max allowed by Solana RPC
        before_signature = None
        total_fetched = 0
        signature_api_calls = 0

        try:
            # Paginate backwards to get all transaction signatures
            # NOTE: getSignaturesForAddress costs 1 credit per call on Helius paid plans
            while True:
                params = [address, {"limit": batch_size}]
                if before_signature:
                    params[1]["before"] = before_signature

                # Fetch batch of signatures
                signatures = self._rpc_call("getSignaturesForAddress", params)
                signature_api_calls += 1  # 1 credit per pagination call

                if not signatures:
                    break

                # If we have a token creation time, filter out transactions before it
                if token_creation_time:
                    filtered_sigs = []
                    found_older_than_creation = False
                    for sig in signatures:
                        sig_time = sig.get("blockTime")
                        if sig_time and sig_time >= token_creation_time:
                            filtered_sigs.append(sig)
                        elif sig_time and sig_time < token_creation_time:
                            # We've gone past the creation time, stop pagination after this batch
                            found_older_than_creation = True
                            print(
                                f"[Helius] Reached token creation time ({datetime.utcfromtimestamp(token_creation_time)}), stopping pagination"
                            )
                            break

                    # Add any filtered signatures from this batch
                    if filtered_sigs:
                        all_signatures.extend(filtered_sigs)
                        total_fetched += len(filtered_sigs)

                    # Stop if we found older transactions or no more filtered results
                    if found_older_than_creation or (not filtered_sigs and before_signature):
                        break
                else:
                    all_signatures.extend(signatures)
                    total_fetched += len(signatures)

                print(f"[Helius] Fetched {total_fetched} signatures so far ({signature_api_calls} pagination calls)...")

                # If we got fewer than batch_size, we've reached the beginning
                if len(signatures) < batch_size:
                    break

                # Use the last signature as the 'before' cursor for next batch
                before_signature = signatures[-1]["signature"]

                # Safety limit: don't fetch more than 50,000 signatures total
                if total_fetched >= 50000:
                    print(f"[Helius] Reached safety limit of 50,000 signatures")
                    break

            print(
                f"[Helius] Total signatures fetched: {total_fetched} ({signature_api_calls} getSignaturesForAddress calls)"
            )

            # Reverse to get oldest-first, then take the first 'limit' transactions
            all_signatures.reverse()
            earliest_signatures = all_signatures[:limit]

            print(f"[Helius] Processing {len(earliest_signatures)} earliest signatures...")

            # Now fetch full transaction data for these earliest signatures
            # Each getTransaction call costs 1 credit
            all_transactions = []
            transaction_api_calls = 0

            for i, sig_obj in enumerate(earliest_signatures):
                if i % 50 == 0:
                    print(f"[Helius] Progress: {i}/{len(earliest_signatures)} earliest transactions fetched...")

                try:
                    signature = sig_obj["signature"]
                    tx_data = self._rpc_call(
                        "getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
                    )
                    transaction_api_calls += 1  # 1 credit per getTransaction call

                    if tx_data:
                        parsed_tx = self._parse_rpc_transaction(tx_data, signature)
                        if parsed_tx:
                            all_transactions.append(parsed_tx)

                except Exception as tx_error:
                    # Skip individual transaction errors
                    continue

            total_credits = signature_api_calls + transaction_api_calls
            print(f"[Helius] Successfully retrieved {len(all_transactions)} earliest transactions")
            print(
                f"[Helius] API credits used: {signature_api_calls} signature calls + {transaction_api_calls} transaction calls = {total_credits} total"
            )
            return all_transactions, total_credits

        except Exception as e:
            print(f"Error fetching earliest transactions: {str(e)}")
            return [], 0

    def _parse_rpc_transaction(self, tx_data: dict, signature: str) -> dict:
        """
        Parse RPC transaction data into a simplified format.
        Extracts timestamp, type, transfers, etc.
        Also tries to extract token metadata from parsed account data.
        """
        try:
            # Extract block time (timestamp)
            timestamp = tx_data.get("blockTime")

            # Extract transaction details
            transaction = tx_data.get("transaction", {})
            meta = tx_data.get("meta", {})

            # Try to extract token info from parsed account data
            token_metadata = {}
            message = transaction.get("message", {})
            for instruction in message.get("instructions", []):
                if isinstance(instruction, dict):
                    parsed = instruction.get("parsed")
                    if parsed and isinstance(parsed, dict):
                        # Look for token info in parsed instructions
                        info = parsed.get("info", {})
                        if "mint" in info:
                            token_metadata["mint"] = info["mint"]

            # Parse token transfers from meta
            token_transfers = []
            if "postTokenBalances" in meta and "preTokenBalances" in meta:
                pre_balances = {b["accountIndex"]: b for b in meta.get("preTokenBalances", [])}
                post_balances = {b["accountIndex"]: b for b in meta.get("postTokenBalances", [])}

                for account_index, post_bal in post_balances.items():
                    pre_bal = pre_balances.get(account_index, {})

                    # Handle None values from uiAmount
                    pre_ui_amount = pre_bal.get("uiTokenAmount", {}).get("uiAmount")
                    post_ui_amount = post_bal.get("uiTokenAmount", {}).get("uiAmount")

                    # If uiAmount is None, use the raw amount divided by decimals
                    if pre_ui_amount is None:
                        pre_amount_raw = float(pre_bal.get("uiTokenAmount", {}).get("amount", 0))
                        pre_decimals = int(pre_bal.get("uiTokenAmount", {}).get("decimals", 0))
                        pre_amount = pre_amount_raw / (10**pre_decimals) if pre_decimals > 0 else pre_amount_raw
                    else:
                        pre_amount = float(pre_ui_amount)

                    if post_ui_amount is None:
                        post_amount_raw = float(post_bal.get("uiTokenAmount", {}).get("amount", 0))
                        post_decimals = int(post_bal.get("uiTokenAmount", {}).get("decimals", 0))
                        post_amount = post_amount_raw / (10**post_decimals) if post_decimals > 0 else post_amount_raw
                    else:
                        post_amount = float(post_ui_amount)

                    if pre_amount != post_amount:
                        # Get account addresses
                        accounts = transaction.get("message", {}).get("accountKeys", [])
                        if account_index < len(accounts):
                            account_key = accounts[account_index]
                            if isinstance(account_key, dict):
                                account_address = account_key.get("pubkey")
                            else:
                                account_address = account_key

                            token_transfers.append(
                                {
                                    "mint": post_bal.get("mint"),
                                    "toUserAccount": account_address if post_amount > pre_amount else None,
                                    "fromUserAccount": account_address if post_amount < pre_amount else None,
                                    "tokenAmount": abs(post_amount - pre_amount),
                                }
                            )

            # Parse native (SOL) transfers
            native_transfers = []
            if "preBalances" in meta and "postBalances" in meta:
                accounts = transaction.get("message", {}).get("accountKeys", [])
                pre_balances = meta.get("preBalances", [])
                post_balances = meta.get("postBalances", [])

                for i, (pre_bal, post_bal) in enumerate(zip(pre_balances, post_balances)):
                    if pre_bal != post_bal and i < len(accounts):
                        account_key = accounts[i]
                        if isinstance(account_key, dict):
                            account_address = account_key.get("pubkey")
                        else:
                            account_address = account_key

                        native_transfers.append(
                            {
                                "fromUserAccount": account_address if post_bal < pre_bal else None,
                                "toUserAccount": account_address if post_bal > pre_bal else None,
                                "amount": abs(post_bal - pre_bal),
                            }
                        )

            return {
                "signature": signature,
                "timestamp": timestamp,
                "type": "UNKNOWN",  # We'll infer type from transfers
                "tokenTransfers": token_transfers,
                "nativeTransfers": native_transfers,
            }

        except Exception as e:
            return None

    def analyze_token_early_bidders(
        self,
        mint_address: str,
        min_usd: float = 50.0,
        time_window_hours: int = 999999,
        max_transactions: int = 500,
        max_credits: int = 1000,
        max_wallets_to_store: int = 10,
    ) -> Dict:
        """
        Analyze a token to find early bidders.

        Args:
            mint_address: Token mint address to analyze
            min_usd: Minimum USD amount to consider (default: $50)
            time_window_hours: Hours from first transaction to consider (default: 999999, effectively unlimited)
            max_transactions: Maximum transactions to analyze (default: 500)

        Returns:
            Dictionary with analysis results:
            {
                'token_address': str,
                'token_info': dict,
                'first_transaction_time': datetime,
                'analysis_window_end': datetime,
                'early_bidders': [
                    {
                        'wallet_address': str,
                        'first_buy_time': datetime,
                        'total_usd': float,
                        'transaction_count': int,
                        'average_buy_usd': float
                    }
                ],
                'total_unique_buyers': int,
                'total_transactions_analyzed': int
            }
        """
        print(f"[Helius] Analyzing token: {mint_address}")

        # Get token metadata (name, symbol, etc.)
        token_info, metadata_credits = self.get_token_metadata(mint_address)

        # Get market cap using dedicated method (DexScreener + Helius fallback)
        market_cap_usd, market_cap_credits = self.get_market_cap_with_fallback(mint_address)

        if token_info:
            token_name = token_info.get("onChainMetadata", {}).get("metadata", {}).get("name", "Unknown")
            if market_cap_usd:
                print(
                    f"[Helius] Token info: {token_name} (Market Cap: ${market_cap_usd:,.2f}, used {metadata_credits} metadata + {market_cap_credits} market cap credits)"
                )
            else:
                print(
                    f"[Helius] Token info: {token_name} (Market Cap: N/A, used {metadata_credits} metadata + {market_cap_credits} market cap credits)"
                )
        else:
            print(f"[Helius] Token info: Unknown (metadata not available)")

        # First, find the token creation time
        token_creation_time, creation_time_credits = self.get_token_creation_time(mint_address)

        # Get transaction history - fetch earliest transactions starting from token creation
        print(f"[Helius] Fetching up to {max_transactions} EARLIEST transactions...")
        if token_creation_time:
            transactions, transaction_credits = self.get_parsed_transactions(
                mint_address,
                limit=max_transactions,
                get_earliest=True,
                token_creation_time=token_creation_time,
                max_credits=max_credits,
            )
        else:
            # Fallback to old method if we can't determine creation time
            print(f"[Helius] Warning: Could not determine token creation time, using fallback method")
            transactions, transaction_credits = self.get_parsed_transactions(
                mint_address, limit=max_transactions, get_earliest=True, max_credits=max_credits
            )

        print(f"[Helius] Retrieved {len(transactions)} earliest transactions (used {transaction_credits} API credits)")

        if not transactions:
            # Still need to report credits used even if no transactions found
            total_credits = metadata_credits + market_cap_credits + creation_time_credits + transaction_credits
            return {
                "token_address": mint_address,
                "token_info": token_info,
                "market_cap_usd": market_cap_usd,
                "error": "No transactions found",
                "early_bidders": [],
                "total_unique_buyers": 0,
                "total_transactions_analyzed": 0,
                "api_credits_used": total_credits,
            }

        # Find first transaction timestamp
        # Transactions are already in chronological order (oldest first)
        first_tx_time = None
        for tx in transactions:
            if tx.get("timestamp"):
                first_tx_time = datetime.utcfromtimestamp(tx["timestamp"])
                break

        if not first_tx_time:
            # Still need to report credits used even if can't determine time
            total_credits = metadata_credits + market_cap_credits + creation_time_credits + transaction_credits
            return {
                "token_address": mint_address,
                "token_info": token_info,
                "market_cap_usd": market_cap_usd,
                "error": "Could not determine first transaction time",
                "early_bidders": [],
                "total_unique_buyers": 0,
                "total_transactions_analyzed": 0,
                "api_credits_used": total_credits,
            }

        window_end = first_tx_time + timedelta(hours=time_window_hours)
        print(f"[Helius] Analysis window: {first_tx_time} to {window_end}")

        # Track buyers within time window
        buyers = {}  # wallet_address -> {first_buy, total_usd, tx_count}

        # Debug: Track what we're seeing
        total_checked = 0
        within_window = 0
        has_buyer = 0
        meets_threshold = 0
        debug_first_done = False

        for tx in transactions:
            if not tx.get("timestamp"):
                continue

            total_checked += 1

            tx_time = datetime.utcfromtimestamp(tx["timestamp"])

            # Skip transactions outside time window
            if tx_time > window_end:
                continue

            within_window += 1

            # Parse transaction for swap/buy activity (debug first one)
            buyer_wallet, usd_amount = self._extract_buy_info(tx, mint_address, debug_first=not debug_first_done)
            if not debug_first_done:
                debug_first_done = True

            if buyer_wallet and usd_amount:
                has_buyer += 1

                # CRITICAL: Only include on-curve wallets (wallets that can sign transactions)
                if not self.is_wallet_on_curve(buyer_wallet):
                    if not debug_first_done:
                        print(f"[Helius] Skipping off-curve wallet: {buyer_wallet}")
                    continue

                if usd_amount >= min_usd:
                    meets_threshold += 1

                    if buyer_wallet not in buyers:
                        buyers[buyer_wallet] = {
                            "wallet_address": buyer_wallet,
                            "first_buy_time": tx_time,
                            "total_usd": 0.0,
                            "transaction_count": 0,
                        }

                    buyers[buyer_wallet]["total_usd"] += usd_amount
                    buyers[buyer_wallet]["transaction_count"] += 1

                    # Keep earliest buy time
                    if tx_time < buyers[buyer_wallet]["first_buy_time"]:
                        buyers[buyer_wallet]["first_buy_time"] = tx_time

        print(
            f"[Helius] Debug: Checked {total_checked} txs, {within_window} in window, {has_buyer} with buyers, {meets_threshold} meeting threshold"
        )

        # Convert to sorted list (earliest buyers first)
        early_bidders = list(buyers.values())
        for bidder in early_bidders:
            bidder["average_buy_usd"] = bidder["total_usd"] / bidder["transaction_count"]

        early_bidders.sort(key=lambda x: x["first_buy_time"])

        print(f"[Helius] Found {len(early_bidders)} early bidders (>${min_usd} USD)")

        # Limit to max_wallets BEFORE fetching balances to save API credits
        max_wallets = max_wallets_to_store or 10  # Default to 10 if not specified
        if len(early_bidders) > max_wallets:
            print(f"[Helius] Limiting to top {max_wallets} earliest wallets (from {len(early_bidders)} total)")
            early_bidders = early_bidders[:max_wallets]

        # Fetch wallet balances for the limited set of early bidders
        print(f"[Helius] Fetching wallet balances for {len(early_bidders)} wallets...")
        balance_credits = 0
        for bidder in early_bidders:
            wallet_balance_usd, credits = self.get_wallet_balance(bidder["wallet_address"])
            bidder["wallet_balance_usd"] = wallet_balance_usd
            balance_credits += credits

        print(f"[Helius] Wallet balances fetched (used {balance_credits} credits)")

        # Calculate actual API credits used
        total_credits = (
            metadata_credits + market_cap_credits + creation_time_credits + transaction_credits + balance_credits
        )

        print(
            f"[Helius] Total API credits used: {total_credits} ({metadata_credits} metadata + {market_cap_credits} market cap + {creation_time_credits} creation time lookup + {transaction_credits} transactions + {balance_credits} wallet balances)"
        )

        return {
            "token_address": mint_address,
            "token_info": token_info,
            "market_cap_usd": market_cap_usd,
            "first_transaction_time": first_tx_time.isoformat(),
            "analysis_window_end": window_end.isoformat(),
            "early_bidders": early_bidders,
            "total_unique_buyers": len(early_bidders),
            "total_transactions_analyzed": len(transactions),
            "api_credits_used": total_credits,
        }

    def _extract_buy_info(self, tx: dict, mint_address: str, debug_first: bool = False) -> tuple:
        """
        Extract buyer wallet and USD amount from a parsed transaction.
        Returns: (wallet_address, usd_amount) or (None, None)

        For pump.fun tokens, we use SOL amount spent as a proxy for USD value.
        1 SOL ≈ $200 USD (adjust based on current market price)

        IMPORTANT: Token transfers show the associated token account (ATA), but SOL payments
        come from the main wallet. We need to find the largest SOL sender in the transaction
        as the buyer (they're paying for the tokens).
        """
        try:
            native_transfers = tx.get("nativeTransfers", [])
            token_transfers = tx.get("tokenTransfers", [])

            if debug_first:
                print(
                    f"[Debug] Transaction has {len(token_transfers)} token transfers, {len(native_transfers)} native transfers"
                )
                if token_transfers:
                    print(f"[Debug] First token transfer: {token_transfers[0]}")
                if native_transfers:
                    print(f"[Debug] First native transfer: {native_transfers[0]}")

            # Find if someone bought this token (received the token)
            for transfer in token_transfers:
                if transfer.get("mint") == mint_address:
                    # Check if someone received this token (buy)
                    token_recipient = transfer.get("toUserAccount")

                    if debug_first:
                        print(f"[Debug] Found matching mint, token recipient: {token_recipient}")

                    if not token_recipient:
                        continue

                    # NEW APPROACH: Find the wallet that sent SOL in this transaction
                    # Since pump.fun swaps involve sending SOL to get tokens, the buyer
                    # is whoever sent the largest amount of SOL in this transaction

                    largest_sol_payment = 0
                    buyer_wallet = None

                    if debug_first:
                        print(f"[Debug] Looking for SOL payments in {len(native_transfers)} native transfers")

                    for native in native_transfers:
                        sender = native.get("fromUserAccount")
                        receiver = native.get("toUserAccount")
                        amount = native.get("amount", 0)

                        if debug_first:
                            print(
                                f"[Debug] Native transfer: from={sender}, to={receiver}, amount={amount} lamports ({amount/1e9:.4f} SOL)"
                            )

                        # Skip if no sender (e.g., rent refunds)
                        if not sender:
                            continue

                        # The buyer is the one sending SOL (not receiving)
                        # Also, ignore very small amounts (< 0.0001 SOL) as they're likely fees
                        if amount > 100000 and amount > largest_sol_payment:  # > 0.0001 SOL
                            largest_sol_payment = amount
                            buyer_wallet = sender
                            if debug_first:
                                print(f"[Debug] New largest SOL sender: {sender} with {amount/1e9:.4f} SOL")

                    if buyer_wallet and largest_sol_payment > 0:
                        sol_amount = largest_sol_payment / 1e9
                        usd_amount = sol_amount * 200  # 1 SOL ≈ $200 USD

                        if debug_first:
                            print(
                                f"[Debug] FOUND BUYER! Wallet: {buyer_wallet}, SOL: {sol_amount:.4f}, USD: ${usd_amount:.2f}"
                            )

                        return (buyer_wallet, usd_amount)
                    else:
                        if debug_first:
                            print(f"[Debug] No SOL payment found (largest was {largest_sol_payment/1e9:.4f} SOL)")

        except Exception as e:
            # Silently skip parsing errors for individual transactions
            if debug_first:
                print(f"[Debug] Exception in _extract_buy_info: {e}")
            pass

        return (None, None)


def generate_token_acronym(token_name: str, token_symbol: str = None) -> str:
    """
    Generate acronym from token name.

    Examples:
        "Dogecoin Super Mega Moon Edition" → "DSMME"
        "Wrapped SOL" → "WS"
        "Dogecoin" → "DOGE" (first 5 chars if no spaces)
        "AI" → "AI" (keep short names as-is)

    Args:
        token_name: Full token name
        token_symbol: Token symbol (fallback)

    Returns:
        Acronym string
    """
    if not token_name or token_name == "Unknown":
        return token_symbol.upper() if token_symbol else "UNKN"

    # Clean the name
    name = token_name.strip()

    # If name is very short (≤4 chars), use it as-is
    if len(name) <= 4:
        return name.upper()

    # Split by common delimiters (space, hyphen, underscore, dot)
    words = re.split(r"[\s\-_.]+", name)

    # Remove empty strings and common words
    words = [w for w in words if w and w.lower() not in ["the", "a", "an", "of", "and", "or"]]

    # If we have multiple words, use first letter of each
    if len(words) > 1:
        acronym = "".join(word[0].upper() for word in words if word)
        return acronym

    # Single word with no spaces - use first 4-5 characters
    if token_symbol and len(token_symbol) <= 5:
        return token_symbol.upper()

    return name[:5].upper()


def generate_axiom_export(
    early_bidders: List[Dict], token_name: str, token_symbol: str = None, limit: int = 10
) -> List[Dict]:
    """
    Generate Axiom wallet tracker import JSON.

    Args:
        early_bidders: List of buyer dictionaries from analysis
        token_name: Token name for acronym generation
        token_symbol: Token symbol (optional)
        limit: Maximum number of wallets (default: 10)

    Returns:
        List of Axiom wallet tracker entries
    """
    acronym = generate_token_acronym(token_name, token_symbol)

    axiom_wallets = []

    for index, bidder in enumerate(early_bidders[:limit], start=1):
        # Round USD amount to whole number
        first_buy_usd = round(bidder.get("total_usd", bidder.get("first_buy_usd", 0)))

        # Format: (1/10)$54|DSMME
        wallet_name = f"({index}/{limit})${first_buy_usd}|{acronym}"

        axiom_entry = {
            "trackedWalletAddress": bidder["wallet_address"],
            "name": wallet_name,
            "emoji": "#️⃣",
            "alertsOnToast": True,
            "alertsOnBubble": True,
            "alertsOnFeed": True,
            "groups": ["Main"],
            "sound": "bing",
        }

        axiom_wallets.append(axiom_entry)

    return axiom_wallets


class TokenAnalyzer:
    """High-level token analysis interface"""

    def __init__(self, api_key: str):
        self.helius = HeliusAPI(api_key)
        self.api_credits_used = 0  # Track API credits used during analysis

    def analyze_token(
        self,
        mint_address: str,
        min_usd: float = 50.0,
        time_window_hours: int = 999999,
        max_transactions: int = 500,
        max_credits: int = 1000,
        max_wallets_to_store: int = 10,
    ) -> Dict:
        """
        Analyze a token to find early bidders.

        Args:
            mint_address: Token mint address
            min_usd: Minimum USD threshold (default: $50)
            time_window_hours: Analysis window in hours (default: 999999, effectively unlimited)
            max_transactions: Maximum transactions to analyze (default: 500)
            max_credits: Maximum API credits to spend (default: 1000)
            max_wallets_to_store: Maximum wallets to store (default: 10)

        Returns:
            Analysis results dictionary
        """
        return self.helius.analyze_token_early_bidders(
            mint_address=mint_address,
            min_usd=min_usd,
            time_window_hours=time_window_hours,
            max_transactions=max_transactions,
            max_credits=max_credits,
            max_wallets_to_store=max_wallets_to_store,
        )


class WebhookManager:
    """Manages Helius webhooks for wallet monitoring"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.webhook_url = "https://api.helius.xyz/v0/webhooks"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})

    def create_webhook(
        self,
        webhook_url: str,
        wallet_addresses: List[str],
        webhook_type: str = "enhanced",
        transaction_types: List[str] = None,
    ) -> Dict:
        """
        Create a new Helius webhook to monitor wallet addresses.

        Args:
            webhook_url: Your server endpoint to receive webhook notifications
            wallet_addresses: List of wallet addresses to monitor
            webhook_type: Type of webhook ("enhanced" or "raw")
            transaction_types: List of transaction types to monitor (e.g., ["TRANSFER", "SWAP"])

        Returns:
            Webhook creation response with webhook_id
        """
        if transaction_types is None:
            transaction_types = ["TRANSFER", "SWAP", "NFT_SALE", "TOKEN_MINT"]

        payload = {
            "webhookURL": webhook_url,
            "transactionTypes": transaction_types,
            "accountAddresses": wallet_addresses,
            "webhookType": webhook_type,
        }

        try:
            response = self.session.post(f"{self.webhook_url}?api-key={self.api_key}", json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            print(f"[Webhook] Created webhook {result.get('webhookID')} for {len(wallet_addresses)} addresses")
            return result
        except Exception as e:
            raise Exception(f"Failed to create webhook: {str(e)}")

    def update_webhook(
        self,
        webhook_id: str,
        wallet_addresses: List[str] = None,
        webhook_url: str = None,
        transaction_types: List[str] = None,
    ) -> Dict:
        """
        Update an existing webhook.

        Args:
            webhook_id: ID of the webhook to update
            wallet_addresses: New list of wallet addresses (optional)
            webhook_url: New webhook URL (optional)
            transaction_types: New list of transaction types (optional)

        Returns:
            Update response
        """
        payload = {}
        if wallet_addresses is not None:
            payload["accountAddresses"] = wallet_addresses
        if webhook_url is not None:
            payload["webhookURL"] = webhook_url
        if transaction_types is not None:
            payload["transactionTypes"] = transaction_types

        try:
            response = self.session.put(
                f"{self.webhook_url}/{webhook_id}?api-key={self.api_key}", json=payload, timeout=30
            )
            response.raise_for_status()
            result = response.json()
            print(f"[Webhook] Updated webhook {webhook_id}")
            return result
        except Exception as e:
            raise Exception(f"Failed to update webhook: {str(e)}")

    def delete_webhook(self, webhook_id: str) -> bool:
        """
        Delete a webhook.

        Args:
            webhook_id: ID of the webhook to delete

        Returns:
            True if successful
        """
        try:
            response = self.session.delete(f"{self.webhook_url}/{webhook_id}?api-key={self.api_key}", timeout=30)
            response.raise_for_status()
            print(f"[Webhook] Deleted webhook {webhook_id}")
            return True
        except Exception as e:
            raise Exception(f"Failed to delete webhook: {str(e)}")

    def get_webhook(self, webhook_id: str) -> Dict:
        """
        Get details of a specific webhook.

        Args:
            webhook_id: ID of the webhook

        Returns:
            Webhook details
        """
        try:
            response = self.session.get(f"{self.webhook_url}/{webhook_id}?api-key={self.api_key}", timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"Failed to get webhook: {str(e)}")

    def list_webhooks(self) -> List[Dict]:
        """
        List all webhooks for this API key.

        Returns:
            List of webhook objects
        """
        try:
            response = self.session.get(f"{self.webhook_url}?api-key={self.api_key}", timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"Failed to list webhooks: {str(e)}")
