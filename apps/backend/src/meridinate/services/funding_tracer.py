"""
Multi-Hop Funding Tracer

Traces the funding chain of a wallet through multiple hops to find the
ultimate funding source. Reveals hidden clusters where wallets appear
independent at 1 hop but converge at deeper hops.

Each hop costs 100 Helius credits (Wallet API /funded-by).
Results are cached in wallet_enrichment_cache to avoid re-tracing.
"""

import json
from typing import Dict, List, Optional, Any
from meridinate.observability import log_error, log_info
from meridinate import analyzed_tokens_db as db


def trace_funding_chain(
    wallet_address: str,
    helius_api_key: str,
    max_hops: int = 3,
    stop_at_exchanges: bool = True,
) -> Dict[str, Any]:
    """
    Trace the funding chain of a wallet through multiple hops.

    Args:
        wallet_address: Starting wallet address
        helius_api_key: Helius API key
        max_hops: Maximum number of hops to trace (1-5)
        stop_at_exchanges: Whether to stop when hitting a known exchange

    Returns:
        Dict with chain (list of hops), terminal wallet, depth reached, credits used
    """
    from meridinate.helius_api import HeliusAPI

    helius = HeliusAPI(helius_api_key)
    chain = []
    credits_used = 0
    current_address = wallet_address
    visited = {wallet_address}

    for hop in range(max_hops):
        # Check cache first
        cached = _get_cached_funded_by(current_address)
        if cached:
            funder = cached.get("funder")
            funder_name = cached.get("funderName")
            funder_type = cached.get("funderType")
            fund_date = cached.get("date")
            fund_timestamp = cached.get("timestamp")
            fund_amount = cached.get("amount")
            # Helius funded-by API returns 'signature' directly
            tx_signature = cached.get("signature")
        else:
            # Call Helius API
            result, cred = helius.get_wallet_funded_by(current_address)
            credits_used += cred

            if not result or not result.get("funder"):
                chain.append({
                    "hop": hop + 1,
                    "wallet": current_address,
                    "funder": None,
                    "funder_name": None,
                    "funder_type": None,
                    "date": None,
                    "timestamp": None,
                    "amount": None,
                    "tx_signature": None,
                    "stop_reason": "no_funding_source",
                })
                break

            funder = result["funder"]
            funder_name = result.get("funderName")
            funder_type = result.get("funderType")
            fund_date = result.get("date")
            fund_timestamp = result.get("timestamp")
            fund_amount = result.get("amount")
            # Helius funded-by API returns 'signature' directly — zero extra credits
            tx_signature = result.get("signature")

            # Cache the result
            _cache_funded_by(current_address, result)

        chain.append({
            "hop": hop + 1,
            "wallet": current_address,
            "funder": funder,
            "funder_name": funder_name,
            "funder_type": funder_type,
            "date": fund_date,
            "timestamp": fund_timestamp,
            "amount": fund_amount,
            "tx_signature": tx_signature,
            "stop_reason": None,
        })

        # Check stop conditions
        if funder in visited:
            chain[-1]["stop_reason"] = "cycle_detected"
            break

        if funder == current_address:
            chain[-1]["stop_reason"] = "self_funded"
            break

        if stop_at_exchanges and funder_type in ("exchange", "protocol"):
            chain[-1]["stop_reason"] = "exchange_reached"
            break

        # Check identity of the funder
        if stop_at_exchanges:
            cached_identity = _get_cached_identity(funder)
            if not cached_identity:
                identity, id_cred = helius.get_wallet_identity(funder)
                credits_used += id_cred
                if identity and identity.get("name"):
                    _cache_identity(funder, identity)
                    if identity.get("type") in ("exchange", "protocol"):
                        chain[-1]["funder_name"] = identity["name"]
                        chain[-1]["funder_type"] = identity["type"]
                        chain[-1]["stop_reason"] = "exchange_reached"
                        break
            elif cached_identity.get("type") in ("exchange", "protocol"):
                chain[-1]["funder_name"] = cached_identity.get("name")
                chain[-1]["funder_type"] = cached_identity.get("type")
                chain[-1]["stop_reason"] = "exchange_reached"
                break

        visited.add(funder)
        current_address = funder

    # Determine terminal wallet (the deepest funder in the chain)
    terminal = chain[-1]["funder"] if chain and chain[-1]["funder"] else wallet_address
    terminal_name = chain[-1].get("funder_name") if chain else None

    return {
        "wallet_address": wallet_address,
        "chain": chain,
        "terminal_wallet": terminal,
        "terminal_name": terminal_name,
        "depth": len(chain),
        "credits_used": credits_used,
    }


def trace_batch_funding_chains(
    wallet_addresses: List[str],
    helius_api_key: str,
    max_hops: int = 3,
    stop_at_exchanges: bool = True,
) -> Dict[str, Any]:
    """
    Trace funding chains for multiple wallets. Uses caching aggressively
    so shared intermediary wallets are only traced once.

    Returns:
        Dict with results per wallet, deep clusters, total credits
    """
    results = {}
    total_credits = 0

    for addr in wallet_addresses:
        trace = trace_funding_chain(addr, helius_api_key, max_hops, stop_at_exchanges)
        results[addr] = trace
        total_credits += trace["credits_used"]

    # Build deep clusters — group wallets by terminal wallet
    terminal_groups: Dict[str, List[str]] = {}
    for addr, trace in results.items():
        terminal = trace["terminal_wallet"]
        if terminal not in terminal_groups:
            terminal_groups[terminal] = []
        terminal_groups[terminal].append(addr)

    # Also group by intermediate funders at each hop level
    hop_clusters: Dict[int, Dict[str, List[str]]] = {}
    for addr, trace in results.items():
        for hop_entry in trace["chain"]:
            hop_num = hop_entry["hop"]
            funder = hop_entry.get("funder")
            if funder:
                if hop_num not in hop_clusters:
                    hop_clusters[hop_num] = {}
                if funder not in hop_clusters[hop_num]:
                    hop_clusters[hop_num][funder] = []
                hop_clusters[hop_num][funder].append(addr)

    # Filter to clusters with 2+ wallets
    deep_clusters = []
    for terminal, wallets in terminal_groups.items():
        if len(wallets) >= 2:
            deep_clusters.append({
                "terminal_wallet": terminal,
                "terminal_name": results[wallets[0]].get("terminal_name"),
                "wallets": wallets,
                "count": len(wallets),
            })
    deep_clusters.sort(key=lambda c: c["count"], reverse=True)

    return {
        "traces": results,
        "deep_clusters": deep_clusters,
        "hop_clusters": {
            hop: {funder: wallets for funder, wallets in groups.items() if len(wallets) >= 2}
            for hop, groups in hop_clusters.items()
        },
        "total_credits": total_credits,
        "wallets_traced": len(results),
    }


def trace_forward_chain(
    wallet_address: str,
    helius_api_key: str,
    max_hops: int = 2,
    max_recipients_per_hop: int = 10,
) -> Dict[str, Any]:
    """
    Trace where a wallet SENT money (forward hops).

    Uses Helius /wallet/transfers to find outgoing SOL transfers,
    then recursively traces where those recipients sent money.
    Reveals sybil distribution networks where a single funder
    creates multiple wallets that buy the same token.

    Args:
        wallet_address: Starting wallet address
        helius_api_key: Helius API key
        max_hops: Maximum depth (default 2, max 3)
        max_recipients_per_hop: Max recipients to trace per level (default 10)

    Returns:
        Dict with tree structure, total recipients found, credits used
    """
    from meridinate.helius_api import HeliusAPI

    helius = HeliusAPI(helius_api_key)
    credits_used = 0
    visited = {wallet_address}

    def _get_outgoing_recipients(address: str) -> List[Dict]:
        """Get unique SOL recipients from a wallet's outgoing transfers."""
        nonlocal credits_used

        # Check cache for forward transfers
        cached_key = f"forward:{address}"
        cached = _get_cached_forward(address)
        if cached is not None:
            return cached

        transfers_data, cred = helius.get_wallet_transfers(address, limit=100)
        credits_used += cred

        if not transfers_data or "data" not in transfers_data:
            _cache_forward(address, [])
            return []

        # Filter to outgoing SOL transfers (funding events)
        recipients: Dict[str, Dict] = {}
        for tx in transfers_data["data"]:
            # Only outgoing native SOL transfers
            if tx.get("direction") != "outgoing":
                continue
            counterparty = tx.get("counterparty")
            if not counterparty or counterparty == address:
                continue

            # Track the largest SOL transfer to each recipient
            amount = tx.get("amount") or 0
            timestamp = tx.get("timestamp")

            if counterparty not in recipients or amount > (recipients[counterparty].get("amount") or 0):
                recipients[counterparty] = {
                    "address": counterparty,
                    "amount": amount,
                    "timestamp": timestamp,
                    "tx_signature": tx.get("signature"),
                }

        result = sorted(recipients.values(), key=lambda r: r.get("amount") or 0, reverse=True)[:max_recipients_per_hop]
        _cache_forward(address, result)
        return result

    def _build_tree(address: str, depth: int) -> Dict:
        """Recursively build the forward tree."""
        node: Dict[str, Any] = {
            "address": address,
            "children": [],
        }

        if depth >= max_hops:
            return node

        recipients = _get_outgoing_recipients(address)

        for recip in recipients:
            child_addr = recip["address"]
            if child_addr in visited:
                node["children"].append({
                    "address": child_addr,
                    "amount": recip.get("amount"),
                    "timestamp": recip.get("timestamp"),
                    "tx_signature": recip.get("tx_signature"),
                    "children": [],
                    "cycle": True,
                })
                continue

            visited.add(child_addr)

            # Check if this recipient is a known wallet in our DB
            is_known = _check_wallet_in_db(child_addr)

            # Get identity if available
            identity = _get_cached_identity(child_addr)
            is_exchange = identity and identity.get("type") in ("exchange", "protocol") if identity else False

            child_node = _build_tree(child_addr, depth + 1) if not is_exchange else {
                "address": child_addr,
                "children": [],
            }
            child_node["amount"] = recip.get("amount")
            child_node["timestamp"] = recip.get("timestamp")
            child_node["tx_signature"] = recip.get("tx_signature")
            child_node["is_known"] = is_known
            child_node["identity_name"] = identity.get("name") if identity else None
            child_node["identity_type"] = identity.get("type") if identity else None

            node["children"].append(child_node)

        return node

    tree = _build_tree(wallet_address, 0)

    # Flatten all discovered addresses
    all_addresses = list(visited - {wallet_address})

    # Cross-reference with our token database to find cluster activity
    cluster_tokens = _find_shared_tokens(all_addresses) if all_addresses else []

    return {
        "wallet_address": wallet_address,
        "tree": tree,
        "total_recipients": len(all_addresses),
        "cluster_tokens": cluster_tokens,
        "credits_used": credits_used,
        "max_hops": max_hops,
    }


def _check_wallet_in_db(wallet_address: str) -> bool:
    """Check if a wallet exists in our early_buyer_wallets table."""
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM early_buyer_wallets WHERE wallet_address = ? LIMIT 1",
                (wallet_address,)
            )
            return cursor.fetchone() is not None
    except Exception:
        return False


def _find_shared_tokens(wallet_addresses: List[str]) -> List[Dict]:
    """Find tokens that multiple wallets in the forward tree bought."""
    if not wallet_addresses:
        return []
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" * len(wallet_addresses))
            cursor.execute(f"""
                SELECT t.id, t.token_name, t.token_symbol, t.token_address,
                       COUNT(DISTINCT ebw.wallet_address) as buyer_count,
                       GROUP_CONCAT(DISTINCT ebw.wallet_address) as buyers
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens t ON t.id = ebw.token_id
                    AND (t.deleted_at IS NULL OR t.deleted_at = '')
                WHERE ebw.wallet_address IN ({placeholders})
                GROUP BY t.id
                HAVING buyer_count >= 2
                ORDER BY buyer_count DESC
                LIMIT 20
            """, wallet_addresses)
            return [
                {
                    "token_id": row[0],
                    "token_name": row[1],
                    "token_symbol": row[2],
                    "token_address": row[3],
                    "buyer_count": row[4],
                    "buyers": row[5].split(",") if row[5] else [],
                }
                for row in cursor.fetchall()
            ]
    except Exception:
        return []


def _get_cached_forward(wallet_address: str) -> Optional[List]:
    """Get cached forward transfer results."""
    try:
        data = db.get_wallet_enrichment(wallet_address)
        if data and data.get("forward_transfers_json"):
            return json.loads(data["forward_transfers_json"])
    except Exception:
        pass
    return None


def _cache_forward(wallet_address: str, recipients: List):
    """Cache forward transfer results."""
    try:
        db.upsert_wallet_enrichment(wallet_address, forward_transfers_json=json.dumps(recipients))
    except Exception:
        pass


# ============================================================================
# Cache helpers (read/write wallet_enrichment_cache)
# ============================================================================

def _get_cached_funded_by(wallet_address: str) -> Optional[Dict]:
    try:
        data = db.get_wallet_enrichment(wallet_address)
        if data and data.get("funded_by_json"):
            return json.loads(data["funded_by_json"])
    except Exception:
        pass
    return None


def _cache_funded_by(wallet_address: str, funded_by: Dict):
    try:
        db.upsert_wallet_enrichment(wallet_address, funded_by_json=json.dumps(funded_by))
    except Exception:
        pass


def _get_cached_identity(wallet_address: str) -> Optional[Dict]:
    try:
        data = db.get_wallet_enrichment(wallet_address)
        if data and data.get("identity_json"):
            return json.loads(data["identity_json"])
    except Exception:
        pass
    return None


def _cache_identity(wallet_address: str, identity: Dict):
    try:
        db.upsert_wallet_enrichment(wallet_address, identity_json=json.dumps(identity))
    except Exception:
        pass
