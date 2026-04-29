"""
Token Scoring Engine

Computes 3 scores for each token:
  1. Momentum Score (0-100): How well is the token performing right now?
  2. Smart Money Score (0-100): How much "smart money" interest does this token have?
  3. Risk Score (0-100): How risky is this token? (lower = safer)

Composite Score = weighted average of all three.
"""

import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_error, log_info


# ============================================================================
# Helius Token Metadata (mint authority, supply, holder distribution)
# ============================================================================

def fetch_token_metadata_from_helius(token_address: str, helius_api_key: str) -> Dict[str, Any]:
    """
    Fetch mint authority, freeze authority, and supply from Helius.
    Costs 2 credits total (getAccountInfo + getTokenSupply).
    """
    import requests

    rpc_url = f"https://mainnet.helius-rpc.com/?api-key={helius_api_key}"
    result = {
        "mint_authority_revoked": None,
        "freeze_authority_active": None,
        "token_supply": None,
    }

    try:
        # getAccountInfo on the mint — reveals mint/freeze authority
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "getAccountInfo",
            "params": [token_address, {"encoding": "jsonParsed"}]
        }
        resp = requests.post(rpc_url, json=payload, timeout=10)
        data = resp.json().get("result", {}).get("value", {})
        if data:
            parsed = data.get("data", {})
            if isinstance(parsed, dict) and "parsed" in parsed:
                info = parsed["parsed"].get("info", {})
                mint_auth = info.get("mintAuthority")
                freeze_auth = info.get("freezeAuthority")
                result["mint_authority_revoked"] = mint_auth is None
                result["freeze_authority_active"] = freeze_auth is not None
                supply_str = info.get("supply")
                decimals = info.get("decimals", 6)
                if supply_str:
                    result["token_supply"] = int(supply_str) / (10 ** decimals)
    except Exception as e:
        log_error(f"[TokenScorer] Helius metadata error for {token_address[:12]}: {e}")

    return result


def fetch_holder_distribution(token_address: str, helius_api_key: str) -> Dict[str, Any]:
    """
    Fetch top holder distribution from Helius getTokenLargestAccounts.
    Costs 1 credit (+ 1 for supply = 2 total).

    Returns holder_top1_pct, holder_top10_pct, holder_count, and holder_addresses.
    """
    import requests

    rpc_url = f"https://mainnet.helius-rpc.com/?api-key={helius_api_key}"
    result = {"holder_top1_pct": None, "holder_top10_pct": None, "holder_count": None, "holder_addresses": []}

    try:
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "getTokenLargestAccounts",
            "params": [token_address]
        }
        resp = requests.post(rpc_url, json=payload, timeout=10)
        accounts = resp.json().get("result", {}).get("value", [])

        if accounts:
            # Get total supply for percentage calculation
            supply_payload = {
                "jsonrpc": "2.0", "id": 2,
                "method": "getTokenSupply",
                "params": [token_address]
            }
            supply_resp = requests.post(rpc_url, json=supply_payload, timeout=10)
            supply_data = supply_resp.json().get("result", {}).get("value", {})
            total_supply = float(supply_data.get("uiAmount", 0)) or 1

            amounts = [float(a.get("uiAmount", 0) or a.get("amount", 0)) for a in accounts]
            addresses = [a.get("address", "") for a in accounts]
            if amounts:
                result["holder_top1_pct"] = (amounts[0] / total_supply * 100) if total_supply > 0 else 0
                top10_sum = sum(amounts[:10])
                result["holder_top10_pct"] = (top10_sum / total_supply * 100) if total_supply > 0 else 0
                result["holder_count"] = len(accounts)
                result["holder_addresses"] = addresses
    except Exception as e:
        log_error(f"[TokenScorer] Holder distribution error for {token_address[:12]}: {e}")

    return result


# ============================================================================
# Scoring Functions
# ============================================================================

def compute_momentum_score(token: Dict) -> float:
    """
    Momentum Score (0-100): How well is the token performing right now?

    Components:
    - MC ratio (current/analysis): 30 points
    - ATH proximity (current/ATH): 20 points
    - Price trend (5m change): 20 points
    - Volume signal: 15 points
    - Liquidity health: 15 points
    """
    score = 50  # Start neutral

    analysis_mc = token.get("market_cap_usd") or 0
    current_mc = token.get("market_cap_usd_current") or analysis_mc
    ath_mc = token.get("market_cap_ath") or analysis_mc

    # MC ratio (current vs analysis): +30 for 3x+, 0 for flat, -30 for -50%
    if analysis_mc > 0:
        mc_ratio = current_mc / analysis_mc
        mc_score = min(30, max(-30, (mc_ratio - 1) * 15))
        score += mc_score

    # ATH proximity: +20 if at ATH, 0 if 50% off, -10 if 90% off
    if ath_mc > 0 and current_mc > 0:
        ath_ratio = current_mc / ath_mc
        ath_score = (ath_ratio - 0.5) * 40  # 0.5 = 0 points, 1.0 = 20 points
        score += min(20, max(-10, ath_score))

    # Liquidity health: liquidity/mc ratio
    liquidity = token.get("liquidity_usd") or 0
    if current_mc > 0 and liquidity > 0:
        liq_ratio = liquidity / current_mc
        if liq_ratio > 0.1:  # >10% liquidity ratio = healthy
            score += 10
        elif liq_ratio > 0.05:
            score += 5
        elif liq_ratio < 0.01:  # <1% = dangerously illiquid
            score -= 10

    return max(0, min(100, score))


def compute_smart_money_score(token_id: int) -> float:
    """
    Smart Money Score (0-100): How much "smart money" interest does this token have?

    Based on wallet tags of early bidders:
    - Consistent Winner wallets: +15 each (capped at 45)
    - Sniper wallets: +10 each (capped at 30)
    - Diversified wallets: +8 each (capped at 24)
    - High Value wallets: +5 each (capped at 15)
    - Cluster wallets (sybil): -5 each (capped at -20)
    - Watchlist wallets: +10 each (capped at 20)
    """
    score = 0

    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()

            # Get all early bidder wallets for this token and their tags
            cursor.execute("""
                SELECT ebw.wallet_address,
                    (SELECT GROUP_CONCAT(wt.tag) FROM wallet_tags wt WHERE wt.wallet_address = ebw.wallet_address) as tags
                FROM early_buyer_wallets ebw
                WHERE ebw.token_id = ?
            """, (token_id,))

            winner_count = 0
            sniper_count = 0
            diversified_count = 0
            high_value_count = 0
            cluster_count = 0
            watchlist_count = 0

            for row in cursor.fetchall():
                tags = (row[1] or "").split(",")
                tag_set = {t.strip() for t in tags}

                # Skip Sniper Bots entirely — they buy everything, not a quality signal
                if "Sniper Bot" in tag_set:
                    continue

                for tag in tag_set:
                    if tag == "Consistent Winner": winner_count += 1
                    elif tag == "Sniper": sniper_count += 1
                    elif tag == "Diversified": diversified_count += 1
                    elif tag == "High SOL Balance": high_value_count += 1
                    elif tag == "Cluster": cluster_count += 1
                    elif tag == "Watchlist": watchlist_count += 1

            score += min(45, winner_count * 15)
            score += min(30, sniper_count * 10)
            score += min(24, diversified_count * 8)
            score += min(15, high_value_count * 5)
            score += min(20, watchlist_count * 10)
            score -= min(20, cluster_count * 5)

    except Exception as e:
        log_error(f"[TokenScorer] Smart money score error for token {token_id}: {e}")

    return max(0, min(100, score))


def compute_risk_score(token: Dict) -> float:
    """
    Risk Score (0-100): How risky is this token? Higher = riskier.

    Components:
    - Mint authority NOT revoked: +30 (creator can print tokens)
    - Freeze authority active: +15 (creator can freeze transfers)
    - Top holder >40%: +20 (extreme concentration)
    - Top 10 holders >80%: +10
    - Low liquidity ratio: +15
    - Very new (<1h): +5
    - Cashback coin: -10 (lower rug incentive)
    """
    risk = 0

    # Mint authority
    mint_revoked = token.get("mint_authority_revoked")
    if mint_revoked is False:
        risk += 30  # Creator can mint more tokens
    elif mint_revoked is True:
        risk -= 5  # Good sign

    # Freeze authority
    if token.get("freeze_authority_active"):
        risk += 15

    # Holder concentration
    top1 = token.get("holder_top1_pct") or 0
    top10 = token.get("holder_top10_pct") or 0
    if top1 > 40:
        risk += 20
    elif top1 > 20:
        risk += 10
    if top10 > 80:
        risk += 10

    # Liquidity ratio
    mc = token.get("market_cap_usd_current") or token.get("market_cap_usd") or 0
    liq = token.get("liquidity_usd") or 0
    if mc > 0:
        liq_ratio = liq / mc
        if liq_ratio < 0.01:
            risk += 15
        elif liq_ratio < 0.05:
            risk += 5

    # Age
    ts = token.get("analysis_timestamp")
    if ts:
        try:
            if "T" in str(ts):
                t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            else:
                t = datetime.strptime(str(ts), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - t).total_seconds() / 3600
            if age_hours < 1:
                risk += 5
        except Exception:
            pass

    # Cashback bonus
    if token.get("is_cashback"):
        risk -= 10

    # Analytics upgrade: derived signal penalties
    holder_velocity = token.get("holder_velocity") or 0
    if holder_velocity > 10:
        risk += 10  # Concentration increasing fast

    if token.get("deployer_is_top_holder"):
        risk += 10  # Deployer still holds large bag

    early_overlap = token.get("early_buyer_holder_overlap") or 0
    if early_overlap > 3:
        risk += 5  # Same people controlling supply

    # Meteora stealth-sell detection
    if token.get("has_meteora_pool"):
        risk += 10  # Meteora pool exists for a PumpFun token — unusual
    if token.get("meteora_creator_linked"):
        risk += 25  # Pool creator linked to deployer/insiders — strong rug signal

    return max(0, min(100, risk))


def compute_composite_score(momentum: float, smart_money: float, risk: float,
                            w_momentum: float = 0.4, w_smart: float = 0.35, w_risk: float = 0.25) -> float:
    """
    Composite Score = weighted average.
    Risk is inverted (100 - risk) so higher composite = better.
    """
    inverted_risk = 100 - risk
    return round(momentum * w_momentum + smart_money * w_smart + inverted_risk * w_risk, 1)


# ============================================================================
# Bundle & Stealth Holder Detection (zero credits — pure DB)
# ============================================================================

def _compute_bundle_metrics(token_id: int) -> Dict[str, Any]:
    """
    Detect coordinated buying patterns:

    1. Same-block clustering: early buyers that bought at the exact same second.
       3+ wallets buying in the same second = almost certainly a Jito bundle.
       Returns the number of clusters found and size of the largest cluster.

    2. Stealth holders: wallets that appear in top holders but made suspiciously
       small early buys. A wallet holding 5% of supply but only spending $50 to
       buy is likely a bundler who acquired tokens via coordinated buys, not
       through the detected buy transactions.
    """
    result = {
        "bundle_cluster_count": 0,  # number of same-second clusters (3+ wallets)
        "bundle_cluster_size": 0,   # size of largest cluster
        "stealth_holder_count": 0,  # top holders with small buys
        "stealth_holder_pct": 0.0,  # % of supply held by stealth holders
    }

    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()

            # ---- Same-block clustering ----
            cursor.execute("""
                SELECT first_buy_timestamp, COUNT(*) as cnt,
                       GROUP_CONCAT(wallet_address) as wallets
                FROM early_buyer_wallets
                WHERE token_id = ? AND first_buy_timestamp IS NOT NULL
                GROUP BY first_buy_timestamp
                HAVING cnt >= 3
                ORDER BY cnt DESC
            """, (token_id,))

            clusters = cursor.fetchall()
            if clusters:
                result["bundle_cluster_count"] = len(clusters)
                result["bundle_cluster_size"] = clusters[0][1]  # largest cluster

            # ---- Stealth holder detection ----
            # Get top holders
            cursor.execute(
                "SELECT top_holders_json, market_cap_usd_current FROM analyzed_tokens WHERE id = ?",
                (token_id,)
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                return result

            import json
            try:
                top_holders = json.loads(row[0])
            except Exception:
                return result

            mc = row[1] or 0
            if not isinstance(top_holders, list) or mc <= 0:
                return result

            # Build set of top holder addresses with their supply %
            holder_supply: Dict[str, float] = {}
            for h in top_holders:
                addr = h.get("address", "")
                balance_usd = h.get("token_balance_usd") or 0
                if addr and balance_usd > 0:
                    holder_supply[addr] = balance_usd / mc * 100  # % of supply

            if not holder_supply:
                return result

            # Get early buyer amounts for these top holders
            holder_addrs = list(holder_supply.keys())
            placeholders = ",".join("?" for _ in holder_addrs)
            cursor.execute(f"""
                SELECT wallet_address, total_usd
                FROM early_buyer_wallets
                WHERE token_id = ? AND wallet_address IN ({placeholders})
            """, [token_id] + holder_addrs)

            stealth_count = 0
            stealth_supply = 0.0

            for r in cursor.fetchall():
                wallet_addr = r[0]
                buy_usd = r[1] or 0
                supply_pct = holder_supply.get(wallet_addr, 0)

                # Stealth holder: holds significant supply (>1%) but bought small (<$200)
                # OR: supply % is 10x+ higher than what their buy amount would suggest
                if supply_pct > 1 and buy_usd < 200:
                    stealth_count += 1
                    stealth_supply += supply_pct
                elif supply_pct > 0.5 and buy_usd > 0:
                    expected_supply_pct = (buy_usd / mc) * 100
                    if supply_pct > expected_supply_pct * 10:
                        stealth_count += 1
                        stealth_supply += supply_pct

            result["stealth_holder_count"] = stealth_count
            result["stealth_holder_pct"] = round(min(stealth_supply, 100), 1)

    except Exception as e:
        log_error(f"[TokenScorer] Bundle metrics failed for token {token_id}: {e}")

    return result


# ============================================================================
# Fresh Wallet Metrics (zero credits — pure DB)
# ============================================================================

def _compute_fresh_metrics(token_id: int, market_cap_usd: Optional[float] = None) -> Dict[str, Any]:
    """
    Compute fresh wallet metrics for a token:
    1. fresh_wallet_pct: % of early buyers that are fresh wallets
    2. fresh_at_deploy: fresh wallets that entered within 60 seconds
    3. controlled_supply_score: 0-100 combining fresh@deploy + cluster overlap + deployer holding
    4. fresh_supply_pct: % of token supply (by USD value) held by fresh wallets
    """
    result = {
        "fresh_wallet_pct": 0.0,
        "fresh_at_deploy_count": 0,
        "fresh_at_deploy_total": 0,  # total wallets that entered within 60s
        "controlled_supply_score": 0.0,
        "fresh_supply_pct": 0.0,
    }

    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()

            # Get all early buyers for this token with entry timing
            cursor.execute("""
                SELECT ebw.wallet_address, ebw.avg_entry_seconds, ebw.wallet_balance_usd
                FROM early_buyer_wallets ebw
                WHERE ebw.token_id = ?
            """, (token_id,))
            buyers = cursor.fetchall()

            if not buyers:
                return result

            buyer_addresses = [b[0] for b in buyers]
            total_buyers = len(buyer_addresses)

            # Get fresh tags for these wallets
            placeholders = ",".join("?" for _ in buyer_addresses)
            cursor.execute(f"""
                SELECT wallet_address, tag FROM wallet_tags
                WHERE wallet_address IN ({placeholders})
                AND tag LIKE 'Fresh at Entry%'
            """, buyer_addresses)
            fresh_wallets = set()
            for r in cursor.fetchall():
                fresh_wallets.add(r[0])

            # Get cluster tags for these wallets
            cursor.execute(f"""
                SELECT wallet_address FROM wallet_tags
                WHERE wallet_address IN ({placeholders})
                AND tag = 'Cluster'
            """, buyer_addresses)
            cluster_wallets = set(r[0] for r in cursor.fetchall())

            # 1. Fresh wallet %
            fresh_count = len(fresh_wallets)
            result["fresh_wallet_pct"] = round(fresh_count / total_buyers * 100, 1) if total_buyers > 0 else 0

            # 2. Fresh at deploy (fresh + entered within 60s)
            early_entry_count = 0  # total wallets entering < 60s
            fresh_at_deploy = 0
            for addr, entry_sec, _ in buyers:
                if entry_sec is not None and entry_sec < 60:
                    early_entry_count += 1
                    if addr in fresh_wallets:
                        fresh_at_deploy += 1
            result["fresh_at_deploy_count"] = fresh_at_deploy
            result["fresh_at_deploy_total"] = early_entry_count

            # 3. Fresh supply % (fresh wallet holdings / market cap)
            if market_cap_usd and market_cap_usd > 0:
                fresh_holdings = sum(
                    (bal or 0) for addr, _, bal in buyers if addr in fresh_wallets and bal
                )
                result["fresh_supply_pct"] = round(min(fresh_holdings / market_cap_usd * 100, 100), 1)

            # 4. Controlled supply score (0-100)
            # Factors: fresh@deploy ratio, cluster+fresh overlap, fresh supply concentration
            fresh_cluster_overlap = len(fresh_wallets & cluster_wallets)

            score = 0
            # Fresh at deploy ratio (0-40 points)
            if early_entry_count > 0:
                score += min((fresh_at_deploy / early_entry_count) * 40, 40)
            # Fresh + Cluster overlap (0-30 points)
            if fresh_count > 0:
                score += min((fresh_cluster_overlap / fresh_count) * 30, 30)
            # Fresh supply concentration (0-30 points)
            if result["fresh_supply_pct"] > 0:
                score += min(result["fresh_supply_pct"] / 50 * 30, 30)  # 50%+ supply = max

            result["controlled_supply_score"] = round(score, 1)

    except Exception as e:
        log_error(f"[TokenScorer] Fresh metrics failed for token {token_id}: {e}")

    return result


# ============================================================================
# Main Scoring Job
# ============================================================================

def _needs_holder_refresh(score_updated_at: Optional[str], interval_hours: float) -> bool:
    """Check if holder data needs refreshing based on score_updated_at timestamp."""
    if not score_updated_at:
        return True
    try:
        if "T" in str(score_updated_at):
            last_update = datetime.fromisoformat(str(score_updated_at).replace("Z", "+00:00"))
        else:
            last_update = datetime.strptime(str(score_updated_at), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        hours_elapsed = (datetime.now(timezone.utc) - last_update).total_seconds() / 3600
        return hours_elapsed >= interval_hours
    except Exception:
        return True


def _compute_holder_velocity(
    old_top1_pct: Optional[float],
    new_top1_pct: Optional[float],
    score_updated_at: Optional[str],
) -> Optional[float]:
    """Compute rate of change in top1_pct per hour."""
    if old_top1_pct is None or new_top1_pct is None or not score_updated_at:
        return None
    try:
        if "T" in str(score_updated_at):
            last_update = datetime.fromisoformat(str(score_updated_at).replace("Z", "+00:00"))
        else:
            last_update = datetime.strptime(str(score_updated_at), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        hours_elapsed = (datetime.now(timezone.utc) - last_update).total_seconds() / 3600
        if hours_elapsed < 0.01:  # Avoid division by near-zero
            return 0.0
        return round((new_top1_pct - old_top1_pct) / hours_elapsed, 4)
    except Exception:
        return None


def _check_deployer_in_holders(
    deployer_address: Optional[str], holder_addresses: List[str]
) -> bool:
    """Check if deployer address appears in top holder addresses."""
    if not deployer_address or not holder_addresses:
        return False
    return deployer_address in holder_addresses


def _count_early_buyer_holder_overlap(token_id: int, holder_addresses: List[str]) -> int:
    """Count how many early buyer wallets are also in the current top holders list."""
    if not holder_addresses:
        return 0
    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT wallet_address FROM early_buyer_wallets WHERE token_id = ?",
                (token_id,),
            )
            early_wallets = {row[0] for row in cursor.fetchall()}
        return len(early_wallets & set(holder_addresses))
    except Exception as e:
        log_error(f"[TokenScorer] Early buyer overlap check failed for token {token_id}: {e}")
        return 0


def score_all_tokens(
    helius_api_key: str,
    fetch_metadata: bool = True,
    holder_refresh_interval_hours: float = 1.0,
) -> Dict[str, Any]:
    """
    Score all active tokens. Called by MC tracker after refreshing market caps.

    Args:
        helius_api_key: For fetching mint authority and holder data
        fetch_metadata: Whether to fetch Helius metadata (costs credits). Set False for score-only refresh.
        holder_refresh_interval_hours: Only re-fetch holder data if last update was this many hours ago.

    Returns:
        Summary of scoring results
    """
    result = {"tokens_scored": 0, "metadata_fetched": 0, "holders_refreshed": 0, "credits_used": 0}

    with db.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, token_address, token_name, market_cap_usd, market_cap_usd_current,
                   market_cap_ath, liquidity_usd, analysis_timestamp, is_cashback,
                   mint_authority_revoked, freeze_authority_active, holder_top1_pct,
                   holder_top10_pct, holder_count_latest, score_updated_at,
                   deployer_address, holder_top1_pct_previous, holder_top10_pct_previous,
                   holder_velocity, deployer_is_top_holder, early_buyer_holder_overlap
            FROM analyzed_tokens
            WHERE (deleted_at IS NULL OR deleted_at = '')
        """)
        columns = [desc[0] for desc in cursor.description]
        tokens = [dict(zip(columns, row)) for row in cursor.fetchall()]

    # Batch lists for DB writes after the loop
    metadata_updates = []   # (mint_authority_revoked, freeze_authority_active, token_supply, id)
    holder_updates = []     # (holder_count, old_top1, old_top10, new_top1, new_top10, velocity, deployer_is_top, overlap, id)
    score_updates = []      # (momentum, smart_money, risk, composite, fresh_*, bundle_*, id)

    for token in tokens:
        token_id = token["id"]
        address = token["token_address"]

        # --- Phase 1: Metadata fetch (once) ---
        if fetch_metadata and token.get("mint_authority_revoked") is None:
            try:
                meta = fetch_token_metadata_from_helius(address, helius_api_key)
                result["credits_used"] += 2  # getAccountInfo + getTokenSupply (inside metadata)
                result["metadata_fetched"] += 1

                token.update(meta)

                metadata_updates.append((
                    meta.get("mint_authority_revoked"),
                    meta.get("freeze_authority_active"),
                    meta.get("token_supply"),
                    token_id,
                ))
            except Exception as e:
                log_error(f"[TokenScorer] Metadata fetch failed for {address[:12]}: {e}")

        # --- Phase 1: Holder refresh (every cycle, with interval check) ---
        if fetch_metadata and _needs_holder_refresh(
            token.get("score_updated_at"), holder_refresh_interval_hours
        ):
            try:
                # Store previous values before overwriting
                old_top1 = token.get("holder_top1_pct")
                old_top10 = token.get("holder_top10_pct")

                holder = fetch_holder_distribution(address, helius_api_key)
                result["credits_used"] += 2  # getTokenLargestAccounts + getTokenSupply
                result["holders_refreshed"] += 1

                new_top1 = holder.get("holder_top1_pct")
                new_top10 = holder.get("holder_top10_pct")
                holder_addresses = holder.get("holder_addresses", [])

                # Phase 2: Compute derived signals
                velocity = _compute_holder_velocity(
                    old_top1, new_top1, token.get("score_updated_at")
                )
                deployer_is_top = _check_deployer_in_holders(
                    token.get("deployer_address"), holder_addresses
                )
                overlap = _count_early_buyer_holder_overlap(token_id, holder_addresses)

                # Update token dict for scoring
                token["holder_top1_pct"] = new_top1
                token["holder_top10_pct"] = new_top10
                token["holder_top1_pct_previous"] = old_top1
                token["holder_top10_pct_previous"] = old_top10
                token["holder_velocity"] = velocity
                token["deployer_is_top_holder"] = deployer_is_top
                token["early_buyer_holder_overlap"] = overlap

                holder_updates.append((
                    holder.get("holder_count"),
                    old_top1,
                    old_top10,
                    new_top1,
                    new_top10,
                    velocity,
                    deployer_is_top,
                    overlap,
                    token_id,
                ))
            except Exception as e:
                log_error(f"[TokenScorer] Holder refresh failed for {address[:12]}: {e}")

        # Compute scores (risk now includes derived signals)
        momentum = compute_momentum_score(token)
        smart_money = compute_smart_money_score(token_id)
        risk = compute_risk_score(token)
        composite = compute_composite_score(momentum, smart_money, risk)

        # Compute fresh wallet metrics (zero credits — pure DB)
        fresh_metrics = _compute_fresh_metrics(token_id, token.get("market_cap_usd_current"))

        # Compute bundle/stealth detection (zero credits — pure DB)
        bundle_metrics = _compute_bundle_metrics(token_id)

        score_updates.append((
            momentum, smart_money, risk, composite,
            fresh_metrics["fresh_wallet_pct"],
            fresh_metrics["fresh_at_deploy_count"],
            fresh_metrics["fresh_at_deploy_total"],
            fresh_metrics["controlled_supply_score"],
            fresh_metrics["fresh_supply_pct"],
            bundle_metrics["bundle_cluster_count"],
            bundle_metrics["bundle_cluster_size"],
            bundle_metrics["stealth_holder_count"],
            bundle_metrics["stealth_holder_pct"],
            token_id,
        ))

        result["tokens_scored"] += 1

    # --- Batch DB writes: 1 connection for all updates ---
    with db.get_db_connection() as conn:
        cursor = conn.cursor()

        if metadata_updates:
            cursor.executemany("""
                UPDATE analyzed_tokens SET
                    mint_authority_revoked = ?,
                    freeze_authority_active = ?,
                    token_supply = ?
                WHERE id = ?
            """, metadata_updates)

        if holder_updates:
            cursor.executemany("""
                UPDATE analyzed_tokens SET
                    holder_count_previous = holder_count_latest,
                    holder_count_latest = ?,
                    holder_top1_pct_previous = ?,
                    holder_top10_pct_previous = ?,
                    holder_top1_pct = ?,
                    holder_top10_pct = ?,
                    holder_velocity = ?,
                    deployer_is_top_holder = ?,
                    early_buyer_holder_overlap = ?
                WHERE id = ?
            """, holder_updates)

        if score_updates:
            cursor.executemany("""
                UPDATE analyzed_tokens SET
                    score_momentum = ?,
                    score_smart_money = ?,
                    score_risk = ?,
                    score_composite = ?,
                    score_updated_at = CURRENT_TIMESTAMP,
                    fresh_wallet_pct = ?,
                    fresh_at_deploy_count = ?,
                    fresh_at_deploy_total = ?,
                    controlled_supply_score = ?,
                    fresh_supply_pct = ?,
                    bundle_cluster_count = ?,
                    bundle_cluster_size = ?,
                    stealth_holder_count = ?,
                    stealth_holder_pct = ?
                WHERE id = ?
            """, score_updates)

    log_info(
        f"[TokenScorer] Scored {result['tokens_scored']} tokens, "
        f"fetched metadata for {result['metadata_fetched']}, "
        f"refreshed holders for {result['holders_refreshed']}, "
        f"{result['credits_used']} credits"
    )
    return result
