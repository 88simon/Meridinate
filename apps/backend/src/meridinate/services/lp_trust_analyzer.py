"""
LP Trust Analyzer — Fast liquidity provider trust assessment.

For each pool on a token, identifies the pool creator by querying the pool
address directly (2-3 credits) instead of scanning the token's full
transaction history (100+ credits). Then checks if the creator is
connected to the deployer via funding trace.

Supports: Meteora DLMM, Raydium CLMM, Raydium Constant Product, Orca Whirlpool.
"""

import json
from typing import Any, Dict, List, Optional

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_error, log_info

# Known DEX program IDs
METEORA_DLMM_PROGRAM = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
RAYDIUM_CLMM_PROGRAM = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
RAYDIUM_AMM_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
ORCA_WHIRLPOOL_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"


def analyze_lp_trust(
    token_address: str,
    deployer_address: Optional[str],
    pools: List[Dict],
    api_key: str,
    token_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Analyze liquidity provider trust for a token's pools.

    Args:
        token_address: Token mint address
        deployer_address: Deployer wallet address (from analysis)
        pools: List of pool dicts from DexScreener [{pairAddress, dexId, liquidity, ...}]
        api_key: Helius API key
        token_id: Optional token ID for DB cross-referencing

    Returns:
        {
            pools: [{pool_address, dex, liquidity_usd, creator, deployer_linked, link_type}],
            total_liquidity: float,
            deployer_linked_liquidity: float,
            deployer_linked_pct: float,
            trust_score: int (0-100),
            dca_backing: float,
            credits_used: int,
        }
    """
    from meridinate.helius_api import HeliusAPI

    helius = HeliusAPI(api_key)
    credits_used = 0

    pool_results = []

    for pool in pools[:10]:  # Cap at 10 pools
        pool_address = pool.get("pairAddress") or pool.get("pool_address")
        dex_id = (pool.get("dexId") or pool.get("dex") or "unknown").lower()
        liquidity = pool.get("liquidity", {})
        liquidity_usd = liquidity.get("usd") if isinstance(liquidity, dict) else (liquidity or 0)

        if not pool_address:
            continue

        # Get pool creator by querying the pool address directly
        creator = _get_pool_creator(helius, pool_address)
        credits_used += 2  # ~2 credits (1 sig + 1 tx parse)

        deployer_linked = False
        link_type = None

        if creator and deployer_address:
            # Check direct match
            if creator == deployer_address:
                deployer_linked = True
                link_type = "deployer_is_creator"
            else:
                # Check shared funder (pure DB, zero credits if cached)
                shared = _check_shared_funder(creator, deployer_address)
                if shared:
                    deployer_linked = True
                    link_type = "shared_funder"
                else:
                    # If not cached, trace the creator (100 credits, but cached forever after)
                    creator_funder = _trace_and_cache_funder(helius, creator)
                    credits_used += 100
                    deployer_funder = _get_cached_funder(deployer_address)

                    if creator_funder and deployer_funder and creator_funder == deployer_funder:
                        deployer_linked = True
                        link_type = "shared_funder"

            # Also check if creator is an early buyer of this token
            if not deployer_linked and token_id:
                if _is_early_buyer(creator, token_id):
                    deployer_linked = True
                    link_type = "early_buyer_is_creator"

        pool_results.append({
            "pool_address": pool_address,
            "dex": dex_id,
            "liquidity_usd": round(liquidity_usd, 2) if liquidity_usd else 0,
            "creator": creator,
            "deployer_linked": deployer_linked,
            "link_type": link_type,
        })

    # Compute aggregate metrics
    total_liquidity = sum(p["liquidity_usd"] for p in pool_results)
    deployer_linked_liquidity = sum(
        p["liquidity_usd"] for p in pool_results if p["deployer_linked"]
    )
    deployer_linked_pct = (
        round(deployer_linked_liquidity / total_liquidity * 100)
        if total_liquidity > 0 else 0
    )

    # Trust score: 100 = all independent, 0 = all deployer-controlled
    trust_score = max(0, 100 - deployer_linked_pct)

    return {
        "pools": pool_results,
        "total_liquidity": round(total_liquidity, 2),
        "deployer_linked_liquidity": round(deployer_linked_liquidity, 2),
        "deployer_linked_pct": deployer_linked_pct,
        "trust_score": trust_score,
        "credits_used": credits_used,
    }


def _get_pool_creator(helius, pool_address: str) -> Optional[str]:
    """Get the creator of a pool by finding its earliest transaction signer."""
    try:
        # Get the oldest signatures on the pool address
        sigs = helius._rpc_call(
            "getSignaturesForAddress",
            [pool_address, {"limit": 5}],  # Only need the earliest few
        )
        if not sigs or not isinstance(sigs, list):
            return None

        # The last signature in the list is the oldest (API returns newest first)
        oldest_sig = sigs[-1].get("signature") if sigs else None
        if not oldest_sig:
            return None

        # Parse the creation transaction to find the signer (fee payer)
        tx = helius._rpc_call(
            "getTransaction",
            [oldest_sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
        )
        if not tx:
            return None

        # Fee payer is the pool creator
        account_keys = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
        if account_keys:
            first_key = account_keys[0]
            return first_key.get("pubkey") if isinstance(first_key, dict) else first_key

    except Exception as e:
        log_error(f"[LPTrust] Failed to get pool creator for {pool_address[:12]}: {e}")

    return None


def _check_shared_funder(wallet_a: str, wallet_b: str) -> bool:
    """Check if two wallets share a funder (pure DB, zero credits)."""
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT funded_by_json FROM wallet_enrichment_cache WHERE wallet_address IN (?, ?)",
                (wallet_a, wallet_b),
            )
            rows = cursor.fetchall()
            if len(rows) < 2:
                return False

            funders = []
            for row in rows:
                if row[0]:
                    try:
                        fb = json.loads(row[0])
                        if fb.get("funder"):
                            funders.append(fb["funder"])
                    except Exception:
                        pass

            return len(funders) == 2 and funders[0] == funders[1]
    except Exception:
        return False


def _get_cached_funder(wallet_address: str) -> Optional[str]:
    """Get cached funder for a wallet."""
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT funded_by_json FROM wallet_enrichment_cache WHERE wallet_address = ?",
                (wallet_address,),
            )
            row = cursor.fetchone()
            if row and row[0]:
                fb = json.loads(row[0])
                return fb.get("funder")
    except Exception:
        pass
    return None


def _trace_and_cache_funder(helius, wallet_address: str) -> Optional[str]:
    """Trace a wallet's funder and cache it. Returns the funder address."""
    try:
        result, _ = helius.get_wallet_funded_by(wallet_address)
        if result and result.get("funder"):
            db.upsert_wallet_enrichment(wallet_address, funded_by_json=json.dumps(result))
            return result["funder"]
    except Exception:
        pass
    return None


def _is_early_buyer(wallet_address: str, token_id: int) -> bool:
    """Check if a wallet is an early buyer of a token."""
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM early_buyer_wallets WHERE wallet_address = ? AND token_id = ? LIMIT 1",
                (wallet_address, token_id),
            )
            return cursor.fetchone() is not None
    except Exception:
        return False
