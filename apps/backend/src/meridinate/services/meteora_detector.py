"""
Meteora Stealth-Sell Detector

Detects when PumpFun tokens have Meteora DLMM pools and analyzes LP activity
to identify stealth selling patterns — where ruggers deposit tokens as single-sided
liquidity and extract SOL as buyers push price up through their bins.

Three-phase funnel:
  Phase 1: Detection — DexScreener (free) flags Meteora pools
  Phase 2: Activity — Helius RPC parses LP add/remove transactions (~1 credit per tx)
  Phase 3: Linkage — Pure DB query checks if LP actors are connected to deployer/insiders
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_error, log_info

METEORA_DLMM_PROGRAM = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"


def analyze_meteora_pool(
    token_id: int,
    token_address: str,
    pool_address: str,
    pool_created_at: Optional[int],
    api_key: str,
    max_transactions: int = 500,
) -> Dict[str, Any]:
    """
    Full Meteora pool analysis: find creator, parse LP activity, check linkage.

    Args:
        token_id: Token ID in our database
        token_address: Token mint address
        pool_address: Meteora DLMM pair address from DexScreener
        pool_created_at: Unix timestamp (ms) of pool creation from DexScreener
        api_key: Helius API key
        max_transactions: Max transactions to parse on the pool

    Returns:
        {
            pool_creator: str | None,
            lp_activity: [{wallet, type, token_amount, sol_amount, timestamp}],
            wallets_involved: [str],
            credits_used: int,
            linkage: {linked: bool, link_type: str | None, linked_wallet: str | None},
        }
    """
    from meridinate.helius_api import HeliusAPI

    helius = HeliusAPI(api_key)
    credits_used = 0

    result: Dict[str, Any] = {
        "pool_creator": None,
        "lp_activity": [],
        "wallets_involved": [],
        "credits_used": 0,
        "linkage": {"linked": False, "link_type": None, "linked_wallet": None},
    }

    try:
        # Primary approach: scan the TOKEN's transaction history for Meteora program involvement.
        # This finds ALL Meteora LP actors regardless of whether we know them in advance.
        # Fetch more sigs than we parse — we'll skip non-Meteora ones cheaply.
        # Fetch sigs — we get up to max_transactions but only parse Meteora-flagged ones
        # For high-volume tokens, LP events are near creation, so fetch oldest sigs
        sigs = helius._rpc_call("getSignaturesForAddress", [token_address, {"limit": max_transactions}])
        credits_used += 1

        wallets_seen: set = set()
        lp_events: List[Dict[str, Any]] = []
        meteora_txs_found = 0
        txs_parsed = 0
        max_txs_to_parse = 100  # cap credit usage per token

        if sigs and isinstance(sigs, list):
            for sig_obj in sigs:
                if txs_parsed >= max_txs_to_parse:
                    break

                sig = sig_obj.get("signature")
                if not sig:
                    continue

                try:
                    txs_parsed += 1
                    tx = helius._rpc_call(
                        "getTransaction",
                        [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
                    )
                    credits_used += 1
                    if not tx:
                        continue

                    # Check if this transaction involves the Meteora DLMM program
                    accounts = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
                    account_addrs = [a.get("pubkey", a) if isinstance(a, dict) else a for a in accounts]
                    has_meteora = METEORA_DLMM_PROGRAM in account_addrs
                    if not has_meteora:
                        for ig in tx.get("meta", {}).get("innerInstructions", []):
                            for iix in ig.get("instructions", []):
                                if iix.get("programId") == METEORA_DLMM_PROGRAM:
                                    has_meteora = True
                                    break
                            if has_meteora:
                                break
                    if not has_meteora:
                        continue

                    meteora_txs_found += 1
                    block_time = tx.get("blockTime")
                    timestamp = (
                        datetime.fromtimestamp(block_time, tz=timezone.utc).isoformat()
                        if block_time else None
                    )

                    # Parse token balance deltas from pre/post balances
                    pre_balances = tx.get("meta", {}).get("preTokenBalances", [])
                    post_balances = tx.get("meta", {}).get("postTokenBalances", [])

                    owner_deltas: Dict[str, float] = {}
                    for pre_b in pre_balances:
                        if pre_b.get("mint") != token_address:
                            continue
                        idx = pre_b.get("accountIndex", -1)
                        owner = pre_b.get("owner", "")
                        pre_amt = float(pre_b.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                        post_amt = pre_amt
                        for post_b in post_balances:
                            if post_b.get("accountIndex") == idx:
                                post_amt = float(post_b.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                                break
                        delta = post_amt - pre_amt
                        if abs(delta) > 0.01:
                            owner_deltas[owner] = owner_deltas.get(owner, 0) + delta

                    # SOL balance deltas
                    pre_sol = tx.get("meta", {}).get("preBalances", [])
                    post_sol = tx.get("meta", {}).get("postBalances", [])

                    # Process each owner with a token delta (skip pool-owned accounts)
                    for owner, token_delta in owner_deltas.items():
                        if owner == pool_address:
                            continue

                        owner_sol_delta = 0.0
                        for i, addr in enumerate(account_addrs):
                            if addr == owner and i < len(pre_sol) and i < len(post_sol):
                                owner_sol_delta = (post_sol[i] - pre_sol[i]) / 1e9
                                break

                        token_sent = abs(token_delta) if token_delta < 0 else 0
                        token_received = token_delta if token_delta > 0 else 0
                        sol_sent = abs(owner_sol_delta) if owner_sol_delta < -0.001 else 0
                        sol_received = owner_sol_delta if owner_sol_delta > 0.001 else 0

                        if token_sent < 100 and token_received < 100 and sol_sent < 0.01 and sol_received < 0.01:
                            continue

                        if token_sent > 0 and sol_sent > 0:
                            event_type = "add"
                        elif token_sent > 0 and sol_sent == 0:
                            event_type = "add_single"
                        elif token_received > 0 and sol_received > 0:
                            event_type = "remove"
                        elif token_received > 0 and sol_sent > 0:
                            event_type = "swap"
                        elif token_sent > 0 and sol_received > 0:
                            event_type = "swap_sell"
                        else:
                            event_type = "other"

                        wallets_seen.add(owner)
                        lp_events.append({
                            "wallet": owner,
                            "type": event_type,
                            "token_in": round(token_sent, 2),
                            "token_out": round(token_received, 2),
                            "sol_in": round(sol_sent, 4),
                            "sol_out": round(sol_received, 4),
                            "timestamp": timestamp,
                            "signature": sig,
                        })

                except Exception:
                    continue

        # The pool creator is the wallet with the earliest LP event
        if lp_events:
            earliest = lp_events[-1]
            result["pool_creator"] = earliest.get("wallet")

        result["lp_activity"] = lp_events
        result["wallets_involved"] = list(wallets_seen)

    except Exception as e:
        log_error(f"[MeteoraDet] Pool analysis failed for {pool_address[:12]}: {e}")

    result["credits_used"] = credits_used
    return result


def check_linkage(
    token_id: int,
    deployer_address: Optional[str],
    wallets_involved: List[str],
) -> Dict[str, Any]:
    """
    Check if any Meteora LP wallet is linked to the token's deployer or early buyers.
    Pure DB query, zero credits.

    Returns:
        {linked: bool, link_type: str | None, linked_wallet: str | None}
    """
    if not wallets_involved:
        return {"linked": False, "link_type": None, "linked_wallet": None}

    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()

            # Check 1: Direct deployer match
            if deployer_address and deployer_address in wallets_involved:
                return {
                    "linked": True,
                    "link_type": "deployer_is_lp",
                    "linked_wallet": deployer_address,
                }

            # Check 2: LP wallet is an early buyer
            placeholders = ",".join("?" for _ in wallets_involved)
            cursor.execute(f"""
                SELECT wallet_address FROM early_buyer_wallets
                WHERE token_id = ? AND wallet_address IN ({placeholders})
                LIMIT 1
            """, [token_id] + wallets_involved)
            row = cursor.fetchone()
            if row:
                return {
                    "linked": True,
                    "link_type": "early_buyer_is_lp",
                    "linked_wallet": row[0],
                }

            # Check 3: LP wallet shares funder with deployer
            if deployer_address:
                cursor.execute(
                    "SELECT funded_by_json FROM wallet_enrichment_cache WHERE wallet_address = ?",
                    (deployer_address,),
                )
                deployer_row = cursor.fetchone()
                deployer_funder = None
                if deployer_row and deployer_row[0]:
                    try:
                        fb = json.loads(deployer_row[0])
                        deployer_funder = fb.get("funder")
                    except Exception:
                        pass

                if deployer_funder:
                    for wallet in wallets_involved:
                        cursor.execute(
                            "SELECT funded_by_json FROM wallet_enrichment_cache WHERE wallet_address = ?",
                            (wallet,),
                        )
                        w_row = cursor.fetchone()
                        if w_row and w_row[0]:
                            try:
                                wfb = json.loads(w_row[0])
                                if wfb.get("funder") == deployer_funder:
                                    return {
                                        "linked": True,
                                        "link_type": "shared_funder",
                                        "linked_wallet": wallet,
                                    }
                            except Exception:
                                pass

            # Check 4: LP wallet shares Cluster tag with early buyers
            cursor.execute(f"""
                SELECT wt.wallet_address FROM wallet_tags wt
                WHERE wt.tag = 'Cluster'
                AND wt.wallet_address IN ({placeholders})
                AND EXISTS (
                    SELECT 1 FROM wallet_tags wt2
                    JOIN early_buyer_wallets ebw ON ebw.wallet_address = wt2.wallet_address
                    WHERE ebw.token_id = ? AND wt2.tag = 'Cluster'
                )
                LIMIT 1
            """, wallets_involved + [token_id])
            row = cursor.fetchone()
            if row:
                return {
                    "linked": True,
                    "link_type": "cluster_overlap",
                    "linked_wallet": row[0],
                }

    except Exception as e:
        log_error(f"[MeteoraDet] Linkage check failed for token {token_id}: {e}")

    # Check 5: Coordinated funding analysis (time clusters, shared funders, fresh near creation)
    # This catches 10-15 hop evasion by looking at temporal patterns instead of tracing hops
    try:
        from meridinate.services.funding_cluster_detector import detect_coordinated_funding

        # Combine LP wallets with deployer and early buyers for funding analysis
        all_related: List[str] = list(wallets_involved)
        if deployer_address and deployer_address not in all_related:
            all_related.append(deployer_address)
        try:
            with db.get_db_connection() as conn:
                cursor = conn.cursor()
                placeholders = ",".join("?" for _ in [token_id])
                cursor.execute(
                    "SELECT wallet_address FROM early_buyer_wallets WHERE token_id = ? LIMIT 20",
                    (token_id,),
                )
                for r in cursor.fetchall():
                    if r[0] not in all_related:
                        all_related.append(r[0])
        except Exception:
            pass

        token_created_at = None
        try:
            with db.get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT analysis_timestamp FROM analyzed_tokens WHERE id = ?", (token_id,))
                row = cursor.fetchone()
                if row:
                    token_created_at = row[0]
        except Exception:
            pass

        coordination = detect_coordinated_funding(token_id, all_related, token_created_at)
        if coordination["coordinated"] and coordination["confidence"] in ("high", "medium"):
            linked_wallet = None
            if coordination["shared_funders"]:
                linked_wallet = coordination["shared_funders"][0]["wallets"][0]
            elif coordination["fresh_near_creation"]:
                linked_wallet = coordination["fresh_near_creation"][0]["wallet"]
            return {
                "linked": True,
                "link_type": f"coordinated_funding ({coordination['confidence']})",
                "linked_wallet": linked_wallet,
            }
    except Exception as e:
        log_error(f"[MeteoraDet] Coordinated funding check failed for token {token_id}: {e}")

    return {"linked": False, "link_type": None, "linked_wallet": None}


def process_token_meteora(
    token_id: int,
    token_address: str,
    deployer_address: Optional[str],
    meteora_pools: List[Dict[str, Any]],
    api_key: str,
) -> Dict[str, Any]:
    """
    Full Meteora detection pipeline for a single token.
    Called from MC tracker when DexScreener reports Meteora pools.

    Args:
        token_id: Token ID in analyzed_tokens
        token_address: Token mint address
        deployer_address: Deployer wallet address (may be None)
        meteora_pools: Pool dicts from DexScreener [{pair_address, dex_id, created_at, ...}]
        api_key: Helius API key

    Returns:
        Summary with credits used and detection results
    """
    if not meteora_pools:
        return {"detected": False, "credits_used": 0}

    # Use the pool with most liquidity (most likely the real one)
    pool = max(meteora_pools, key=lambda p: p.get("liquidity_usd", 0) or 0)
    pool_address = pool.get("pair_address")

    if not pool_address:
        return {"detected": False, "credits_used": 0}

    # Phase 2: Analyze LP activity
    analysis = analyze_meteora_pool(
        token_id, token_address, pool_address,
        pool.get("created_at"), api_key,
    )

    # Phase 3: Check linkage
    linkage = check_linkage(token_id, deployer_address, analysis["wallets_involved"])

    # Store results
    pool_created_at = None
    if pool.get("created_at"):
        try:
            pool_created_at = datetime.fromtimestamp(
                pool["created_at"] / 1000, tz=timezone.utc
            ).isoformat()
        except Exception:
            pass

    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE analyzed_tokens SET
                    has_meteora_pool = 1,
                    meteora_pool_address = ?,
                    meteora_pool_created_at = ?,
                    meteora_pool_creator = ?,
                    meteora_creator_linked = ?,
                    meteora_link_type = ?,
                    meteora_lp_activity_json = ?
                WHERE id = ?
            """, (
                pool_address,
                pool_created_at,
                analysis["pool_creator"],
                1 if linkage["linked"] else 0,
                linkage["link_type"],
                json.dumps(analysis["lp_activity"][:20]),  # cap stored activity
                token_id,
            ))

            # Add token tag if linkage confirmed
            if linkage["linked"]:
                cursor.execute(
                    "INSERT OR IGNORE INTO token_tags (token_id, tag, tier, source, updated_at) "
                    "VALUES (?, 'meteora-stealth-sell', 1, 'auto:meteora-detection', CURRENT_TIMESTAMP)",
                    (token_id,),
                )
                log_info(
                    f"[MeteoraDet] Token {token_id}: STEALTH SELL DETECTED — "
                    f"pool creator {analysis['pool_creator'][:12] if analysis['pool_creator'] else '?'}... "
                    f"linked via {linkage['link_type']} to {linkage['linked_wallet'][:12] if linkage['linked_wallet'] else '?'}..."
                )

    except Exception as e:
        log_error(f"[MeteoraDet] Failed to store results for token {token_id}: {e}")

    return {
        "detected": True,
        "pool_address": pool_address,
        "pool_creator": analysis["pool_creator"],
        "lp_events": len(analysis["lp_activity"]),
        "wallets_involved": len(analysis["wallets_involved"]),
        "linked": linkage["linked"],
        "link_type": linkage["link_type"],
        "credits_used": analysis["credits_used"],
    }
