"""
Coordinated Funding Detector

Detects coordinated wallet funding patterns that evade simple funder-matching:
1. Same funder, multiple wallets (exact match, any hop depth in cache)
2. Time-clustered micro-funding (3+ wallets funded within 1 hour from unknown sources)
3. Fresh funding near token creation (wallet funded within 24h of token birth)

All detection is based on data already in wallet_enrichment_cache — zero extra credits.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_info


def detect_coordinated_funding(
    token_id: int,
    wallet_addresses: List[str],
    token_created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Detect coordinated funding among a set of wallets.

    Args:
        token_id: Token ID in analyzed_tokens
        wallet_addresses: List of wallet addresses to check (deployer + buyers + LP actors)
        token_created_at: ISO timestamp of token creation (for freshness check)

    Returns:
        {
            coordinated: bool,
            confidence: str ("high", "medium", "low"),
            signals: [str],  # human-readable descriptions of what was found
            shared_funders: [{funder, wallets: [str], count}],
            time_clusters: [{window_start, wallets: [str], count}],
            fresh_near_creation: [{wallet, funded_at, hours_from_creation}],
        }
    """
    result: Dict[str, Any] = {
        "coordinated": False,
        "confidence": "low",
        "signals": [],
        "shared_funders": [],
        "time_clusters": [],
        "fresh_near_creation": [],
    }

    if len(wallet_addresses) < 2:
        return result

    # Fetch all funding data from cache (zero credits)
    funding_data: List[Dict[str, Any]] = []
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in wallet_addresses)
            cursor.execute(f"""
                SELECT wallet_address, funded_by_json
                FROM wallet_enrichment_cache
                WHERE wallet_address IN ({placeholders})
                AND funded_by_json IS NOT NULL
            """, wallet_addresses)

            for row in cursor.fetchall():
                try:
                    fb = json.loads(row[1])
                    if not isinstance(fb, dict) or not fb.get("funder"):
                        continue
                    funding_data.append({
                        "wallet": row[0],
                        "funder": fb["funder"],
                        "funder_name": fb.get("funderName"),
                        "funder_type": fb.get("funderType"),
                        "amount": fb.get("amount", 0),
                        "timestamp": fb.get("timestamp"),
                        "date": fb.get("date"),
                    })
                except Exception:
                    continue
    except Exception:
        return result

    if len(funding_data) < 2:
        return result

    signals: List[str] = []
    high_confidence = False

    # ================================================================
    # Signal 1: Same funder, multiple wallets (exact match)
    # ================================================================
    funder_to_wallets: Dict[str, List[str]] = {}
    for fd in funding_data:
        funder = fd["funder"]
        # Skip known exchanges — many wallets share exchange funders legitimately
        if fd.get("funder_type") in ("exchange", "Centralized Exchange", "protocol"):
            continue
        if fd.get("funder_name"):  # named entity = exchange/protocol
            continue
        if funder not in funder_to_wallets:
            funder_to_wallets[funder] = []
        funder_to_wallets[funder].append(fd["wallet"])

    shared_funders = []
    for funder, wallets in funder_to_wallets.items():
        if len(wallets) >= 2:
            shared_funders.append({
                "funder": funder,
                "wallets": wallets,
                "count": len(wallets),
            })
            signals.append(
                f"Same unknown funder {funder[:12]}... funded {len(wallets)} wallets"
            )
            high_confidence = True

    result["shared_funders"] = shared_funders

    # ================================================================
    # Signal 2: Time-clustered micro-funding
    # 3+ wallets funded within 1 hour, all from unknown wallets, all < 1 SOL
    # ================================================================
    # Only consider wallets funded from unknown sources with small amounts
    micro_funded = [
        fd for fd in funding_data
        if fd.get("timestamp")
        and not fd.get("funder_name")
        and fd.get("funder_type") not in ("exchange", "Centralized Exchange", "protocol")
        and (fd.get("amount") or 0) < 1.0
    ]

    time_clusters = []
    used_in_cluster: Set[str] = set()

    # Sort by timestamp
    micro_funded.sort(key=lambda x: x["timestamp"] or 0)

    for i, fd1 in enumerate(micro_funded):
        if fd1["wallet"] in used_in_cluster:
            continue
        ts1 = fd1["timestamp"]
        if not ts1:
            continue

        cluster = [fd1]
        for j, fd2 in enumerate(micro_funded):
            if i == j or fd2["wallet"] in used_in_cluster:
                continue
            ts2 = fd2.get("timestamp")
            if ts2 and abs(ts2 - ts1) <= 3600:  # within 1 hour
                cluster.append(fd2)

        if len(cluster) >= 3:
            for c in cluster:
                used_in_cluster.add(c["wallet"])
            time_clusters.append({
                "window_start": fd1["date"],
                "wallets": [c["wallet"] for c in cluster],
                "count": len(cluster),
            })
            signals.append(
                f"Time cluster: {len(cluster)} wallets micro-funded within 1 hour around {fd1['date'][:19]}"
            )
            high_confidence = True

    result["time_clusters"] = time_clusters

    # ================================================================
    # Signal 3: Fresh funding near token creation
    # Wallet funded within 24h of token creation from unknown source
    # ================================================================
    token_ts = None
    if token_created_at:
        try:
            if "T" in str(token_created_at):
                token_ts = datetime.fromisoformat(
                    str(token_created_at).replace("Z", "+00:00")
                ).timestamp()
            else:
                token_ts = datetime.strptime(
                    str(token_created_at), "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            pass

    if not token_ts:
        # Try to get from DB
        try:
            with db.get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT analysis_timestamp FROM analyzed_tokens WHERE id = ?",
                    (token_id,),
                )
                row = cursor.fetchone()
                if row and row[0]:
                    ts_str = str(row[0])
                    if "T" in ts_str:
                        token_ts = datetime.fromisoformat(
                            ts_str.replace("Z", "+00:00")
                        ).timestamp()
                    else:
                        token_ts = datetime.strptime(
                            ts_str, "%Y-%m-%d %H:%M:%S"
                        ).replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            pass

    fresh_near_creation = []
    if token_ts:
        for fd in funding_data:
            fund_ts = fd.get("timestamp")
            if not fund_ts:
                continue
            # Skip exchange-funded wallets
            if fd.get("funder_name") or fd.get("funder_type") in (
                "exchange", "Centralized Exchange", "protocol"
            ):
                continue

            hours_diff = abs(fund_ts - token_ts) / 3600
            if hours_diff <= 24:
                fresh_near_creation.append({
                    "wallet": fd["wallet"],
                    "funded_at": fd["date"],
                    "hours_from_creation": round(hours_diff, 1),
                    "amount": fd.get("amount", 0),
                })
                signals.append(
                    f"Wallet {fd['wallet'][:12]}... funded {hours_diff:.1f}h from token creation ({fd.get('amount', 0):.3f} SOL)"
                )

    result["fresh_near_creation"] = fresh_near_creation

    # ================================================================
    # Determine overall confidence
    # ================================================================
    if high_confidence:
        result["coordinated"] = True
        result["confidence"] = "high"
    elif len(fresh_near_creation) >= 2:
        result["coordinated"] = True
        result["confidence"] = "medium"
    elif len(fresh_near_creation) >= 1 and len(funding_data) >= 3:
        result["coordinated"] = True
        result["confidence"] = "low"

    result["signals"] = signals
    return result
