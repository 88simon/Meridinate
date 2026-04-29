"""
Tokens router - token management endpoints

Provides REST endpoints for token history, details, trash management, and exports
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import asyncio

import aiosqlite
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from meridinate.middleware.rate_limit import MARKET_CAP_RATE_LIMIT, READ_RATE_LIMIT, conditional_rate_limit
from meridinate.observability import log_error, log_info

from meridinate import analyzed_tokens_db as db
from meridinate import settings
from meridinate.settings import CURRENT_INGEST_SETTINGS
from meridinate.cache import ResponseCache
from meridinate.utils.models import (
    AnalysisHistory,
    MessageResponse,
    RefreshMarketCapResult,
    RefreshMarketCapsRequest,
    RefreshMarketCapsResponse,
    TokenDetail,
    TokensResponse,
    TokenTagRequest,
    TokenTagsResponse,
    TopHoldersResponse,
    UpdateVerdictRequest,
)
from meridinate.helius_api import HeliusAPI
from meridinate.credit_tracker import credit_tracker, get_credit_tracker, CreditOperation

router = APIRouter()
cache = ResponseCache(name="tokens_history")


def _parse_token_age(analysis_timestamp) -> Optional[timedelta]:
    """Parse analysis_timestamp and return age as timedelta, or None."""
    if not analysis_timestamp or not isinstance(analysis_timestamp, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            dt = datetime.strptime(analysis_timestamp, fmt).replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) - dt
        except ValueError:
            continue
    return None


async def compute_auto_verdict(
    conn: aiosqlite.Connection,
    token_id: int,
    market_cap_usd_original: float,
    market_cap_usd_current: float,
    market_cap_ath: float,
    analysis_timestamp: str,
) -> Optional[str]:
    """
    Compute an auto-verdict for a token based on MC performance and store it as a token tag.

    Rules:
    - Win 1:  ATH >= 3x original MC AND current >= 1x original MC -> verified-win
    - Win 2:  ATH >= 1.5x AND current >= 1.5x original MC -> verified-win
    - Loss 1: current < 0.1x original MC AND age >= 6h -> verified-loss
    - Loss 2: 72h+ old AND current < 0.3x original MC -> verified-loss
    - Loss 3: current < 1000 AND age >= 24h -> verified-loss (dead token)

    Will NOT overwrite manual (tier=3) verdicts.
    """
    if not market_cap_usd_original or market_cap_usd_original <= 0:
        return None

    # Check if a manual verdict already exists (tier=3 means manual)
    cursor = await conn.execute(
        "SELECT tag, tier FROM token_tags WHERE token_id = ? AND tag IN ('verified-win', 'verified-loss') AND tier = 3",
        (token_id,),
    )
    manual_verdict = await cursor.fetchone()
    if manual_verdict:
        return None  # Don't overwrite manual verdicts

    verdict = None

    # Rule 1: ATH was 3x+ above analysis MC AND current still >= 1x
    if (
        market_cap_ath
        and market_cap_usd_current
        and market_cap_ath >= market_cap_usd_original * 3
        and market_cap_usd_current >= market_cap_usd_original
    ):
        verdict = "verified-win"

    # Rule 2: ATH >= 1.5x AND current >= 1.5x
    elif (
        market_cap_ath
        and market_cap_usd_current
        and market_cap_ath >= market_cap_usd_original * 1.5
        and market_cap_usd_current >= market_cap_usd_original * 1.5
    ):
        verdict = "verified-win"

    # Rule 3 (Loss 1): current < 0.1x (lost 90%+) AND age >= 6h
    elif market_cap_usd_current and market_cap_usd_current < market_cap_usd_original * 0.1:
        age = _parse_token_age(analysis_timestamp)
        if age and age >= timedelta(hours=6):
            verdict = "verified-loss"

    # Rule 4 (Loss 2): 72h+ old AND current < 0.3x
    elif market_cap_usd_current and market_cap_usd_current < market_cap_usd_original * 0.3:
        age = _parse_token_age(analysis_timestamp)
        if age and age >= timedelta(hours=72):
            verdict = "verified-loss"

    # Rule 5 (Loss 3): dead token - current < 1000 AND age >= 24h
    elif market_cap_usd_current is not None and market_cap_usd_current < 1000:
        age = _parse_token_age(analysis_timestamp)
        if age and age >= timedelta(hours=24):
            verdict = "verified-loss"

    if verdict:
        from meridinate.tasks.mc_tracker import WIN_MULTIPLIER_TIERS, WIN_MULTIPLIER_TAGS

        # Remove existing auto-verdicts and multiplier tags
        await conn.execute(
            "DELETE FROM token_tags WHERE token_id = ? AND tag IN ('verified-win', 'verified-loss') AND (tier = 1 OR source = 'auto:mc-performance')",
            (token_id,),
        )
        placeholders = ",".join("?" for _ in WIN_MULTIPLIER_TAGS)
        await conn.execute(
            f"DELETE FROM token_tags WHERE token_id = ? AND tag IN ({placeholders})",
            [token_id] + WIN_MULTIPLIER_TAGS,
        )
        # Insert verdict
        await conn.execute(
            """
            INSERT INTO token_tags (token_id, tag, tier, source, updated_at)
            VALUES (?, ?, 1, 'auto:mc-performance', CURRENT_TIMESTAMP)
            """,
            (token_id, verdict),
        )
        # Insert win multiplier tag
        if verdict == "verified-win" and market_cap_ath and market_cap_usd_original > 0:
            multiple = market_cap_ath / market_cap_usd_original
            for min_mult, tag in WIN_MULTIPLIER_TIERS:
                if multiple >= min_mult:
                    await conn.execute(
                        "INSERT OR IGNORE INTO token_tags (token_id, tag, tier, source, updated_at) VALUES (?, ?, 1, 'auto:mc-performance', CURRENT_TIMESTAMP)",
                        (token_id, tag),
                    )
                    break

        log_info(f"[AutoVerdict] Token {token_id}: {verdict} (original=${market_cap_usd_original:,.0f}, current=${market_cap_usd_current or 0:,.0f}, ath=${market_cap_ath or 0:,.0f})")

    return verdict


def _table_has_column(db_path: str, table: str, column: str) -> bool:
    """Check once at startup whether a table has a specific column."""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(f"PRAGMA table_info({table})")
            return any(row[1] == column for row in cursor.fetchall())
    except Exception:
        return False


HAS_LIQUIDITY_USD_COLUMN = _table_has_column(settings.DATABASE_FILE, "analyzed_tokens", "liquidity_usd")
LIQUIDITY_SELECT_EXPR = "t.liquidity_usd" if HAS_LIQUIDITY_USD_COLUMN else "NULL AS liquidity_usd"


class LatestTokenResponse(BaseModel):
    """Response model for the latest analyzed token."""

    token_id: Optional[int] = None
    token_name: Optional[str] = None
    token_symbol: Optional[str] = None
    analysis_timestamp: Optional[str] = None
    wallets_found: Optional[int] = None
    credits_used: Optional[int] = None


@router.get("/api/tokens/latest", response_model=LatestTokenResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_latest_token(request: Request):
    """
    Get the most recently analyzed token.

    Returns lightweight data for status bar display:
    - token_id, token_name, token_symbol
    - analysis_timestamp
    - wallets_found, credits_used
    """
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        query = """
            SELECT
                t.id as token_id,
                t.token_name,
                t.token_symbol,
                t.analysis_timestamp,
                COUNT(DISTINCT ebw.wallet_address) as wallets_found,
                COALESCE(t.last_analysis_credits, t.credits_used) as credits_used
            FROM analyzed_tokens t
            LEFT JOIN early_buyer_wallets ebw ON ebw.token_id = t.id
            WHERE t.deleted_at IS NULL OR t.deleted_at = ''
            GROUP BY t.id
            ORDER BY t.analysis_timestamp DESC
            LIMIT 1
        """
        cursor = await conn.execute(query)
        row = await cursor.fetchone()

        if not row:
            return LatestTokenResponse()

        return LatestTokenResponse(
            token_id=row["token_id"],
            token_name=row["token_name"],
            token_symbol=row["token_symbol"],
            analysis_timestamp=row["analysis_timestamp"],
            wallets_found=row["wallets_found"],
            credits_used=row["credits_used"],
        )


def compute_token_labels(
    token_dict: Dict[str, Any],
    swab_data: Dict[str, Any],
    manual_tags: List[str],
    signal_labels: Optional[List[str]] = None,
) -> List[str]:
    """
    Compute the 3-tier label system for a token.

    Tier 1 -- MC-based auto-labels (prefixed 'auto:'):
      Mooning, Climbing, Stable, Declining, Dead, ATH
    Operational labels (also 'auto:' prefix, unchanged):
      Position-Tracked, No-Positions, Exited, Manual, TIP, Discarded

    Tier 2 -- Wallet-signal labels (prefixed 'signal:'):
      Smart-Money, Cluster-Alert, Insider-Heavy, Bot-Heavy, Whale-Backed
      These are computed separately via compute_token_signal_labels() and
      passed in through the signal_labels parameter.

    Tier 3 -- Manual labels (prefixed 'tag:'):
      verified-win, verified-loss, watching

    Args:
        token_dict: Token data from database (must include market_cap_usd,
                    market_cap_usd_current, market_cap_ath, market_cap_updated_at)
        swab_data: Position aggregates for this token
        manual_tags: List of manual tags from token_tags table
        signal_labels: Pre-computed Tier 2 signal labels (optional)

    Returns:
        Combined list of all tier labels
    """
    labels: List[str] = []

    # ── Tier 1: Source labels (operational, kept as-is) ──────────────
    ingest_source = token_dict.get("ingest_source")
    if ingest_source == "manual":
        labels.append("auto:Manual")
    elif ingest_source == "dexscreener":
        labels.append("auto:TIP")

    # ── Tier 1: Position exposure labels (operational, kept as-is) ──
    open_positions = swab_data.get("open_positions", 0)
    webhook_active = bool(token_dict.get("webhook_id"))

    if open_positions > 0 or webhook_active:
        labels.append("auto:Position-Tracked")
    elif swab_data.get("realized_pnl_usd") is not None and open_positions == 0:
        labels.append("auto:Exited")
    else:
        labels.append("auto:No-Positions")

    # ── Tier 1: MC-based auto-labels ────────────────────────────────
    analysis_mc = token_dict.get("market_cap_usd")  # MC at time of analysis
    current_mc = token_dict.get("market_cap_usd_current") or analysis_mc
    ath_mc = token_dict.get("market_cap_ath")
    market_cap_updated_at = token_dict.get("market_cap_updated_at")

    # Check Dead first (takes priority -- no point labelling a dead token as Stable)
    is_dead = False
    if current_mc is not None and current_mc < 1000:
        labels.append("auto:Dead")
        is_dead = True

    # Check staleness: no MC data updated in 72+ hours -> Dead
    if not is_dead and market_cap_updated_at:
        try:
            updated = datetime.fromisoformat(market_cap_updated_at.replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            hours_since_update = (now - updated).total_seconds() / 3600
            if hours_since_update > 72:
                labels.append("auto:Dead")
                is_dead = True
        except (ValueError, TypeError):
            pass

    # MC movement labels (only if not dead and we have both MCs)
    if not is_dead and analysis_mc and current_mc:
        ratio = current_mc / analysis_mc
        if ratio > 3.0:
            labels.append("auto:Mooning")
        elif ratio > 1.5:
            labels.append("auto:Climbing")
        elif ratio >= 0.7:
            labels.append("auto:Stable")
        elif ratio < 0.5:
            labels.append("auto:Declining")
        # ratio between 0.5 and 0.7 gets no MC movement label (mild decline)

    # ATH proximity label (within 5% of all-time high)
    if current_mc and ath_mc and ath_mc > 0:
        if current_mc >= ath_mc * 0.95:
            labels.append("auto:ATH")

    # Discarded label (operational)
    if token_dict.get("deleted_at"):
        labels.append("auto:Discarded")

    # ── Tier 2: Wallet-signal labels (pre-computed, passed in) ──────
    if signal_labels:
        labels.extend(signal_labels)

    # ── Tier 3: Manual tags ─────────────────────────────────────────
    for tag in manual_tags:
        labels.append(f"tag:{tag}")

    return labels


def compute_token_signal_labels(token_id: int) -> List[str]:
    """
    Compute Tier 2 wallet-signal labels for a token by inspecting the
    wallet_tags of its early buyer wallets.

    This is a synchronous function that queries the database directly.
    Call it via asyncio.to_thread() from async contexts.

    Signal labels (prefixed 'signal:'):
      - Smart-Money:   3+ early bidders tagged "Consistent Winner" or "High SOL Balance"
      - Cluster-Alert: 3+ early bidders share a "Cluster" tag
      - Insider-Heavy: any early bidder tagged "Insider" or "KOL"
      - Bot-Heavy:     50%+ of early bidders tagged "Low Value" or "Cluster"
      - Whale-Backed:  any early bidder tagged "High SOL Balance"

    Args:
        token_id: Database ID of the token

    Returns:
        List of signal labels (may be empty)
    """
    labels: List[str] = []

    try:
        with sqlite3.connect(settings.DATABASE_FILE) as conn:
            # Get distinct early buyer wallet addresses for this token
            cursor = conn.execute(
                "SELECT DISTINCT wallet_address FROM early_buyer_wallets WHERE token_id = ?",
                (token_id,),
            )
            wallet_addresses = [row[0] for row in cursor.fetchall()]

            if not wallet_addresses:
                return labels

            # Fetch all wallet tags for these addresses in one query
            placeholders = ",".join("?" * len(wallet_addresses))
            cursor = conn.execute(
                f"SELECT wallet_address, tag FROM wallet_tags WHERE wallet_address IN ({placeholders})",
                wallet_addresses,
            )

            # Build a mapping: wallet_address -> set of tags
            tags_by_wallet: Dict[str, set] = {addr: set() for addr in wallet_addresses}
            for row in cursor.fetchall():
                addr, tag = row[0], row[1]
                if addr in tags_by_wallet:
                    tags_by_wallet[addr].add(tag)

            total_wallets = len(wallet_addresses)

            # Counters for signal evaluation
            smart_money_count = 0
            cluster_count = 0
            insider_found = False
            whale_found = False
            bot_count = 0

            for addr in wallet_addresses:
                tags = tags_by_wallet.get(addr, set())

                # Skip Sniper Bots — they buy everything, not a quality signal
                if "Sniper Bot" in tags:
                    bot_count += 1
                    continue

                if "Consistent Winner" in tags or "High SOL Balance" in tags:
                    smart_money_count += 1
                if "Cluster" in tags:
                    cluster_count += 1
                if "Insider" in tags or "KOL" in tags:
                    insider_found = True
                if "High SOL Balance" in tags:
                    whale_found = True
                if "Low Value" in tags or "Cluster" in tags:
                    bot_count += 1

            # Apply thresholds
            if smart_money_count >= 3:
                labels.append("signal:Smart-Money")
            if cluster_count >= 3:
                labels.append("signal:Cluster-Alert")
            if insider_found:
                labels.append("signal:Insider-Heavy")
            if total_wallets > 0 and (bot_count / total_wallets) >= 0.5:
                labels.append("signal:Bot-Heavy")
            if whale_found:
                labels.append("signal:Whale-Backed")

            # Smart money flow direction from position tracking
            cursor = conn.execute(
                "SELECT smart_money_flow FROM analyzed_tokens WHERE id = ?",
                (token_id,),
            )
            flow_row = cursor.fetchone()
            if flow_row and flow_row[0]:
                try:
                    flow = json.loads(flow_row[0]) if isinstance(flow_row[0], str) else flow_row[0]
                    direction = flow.get("flow_direction")
                    if direction == "bullish":
                        labels.append("signal:Smart-Bullish")
                    elif direction == "bearish":
                        labels.append("signal:Smart-Bearish")
                except Exception:
                    pass

    except Exception:
        # Signal labels are best-effort; don't break token listing on DB errors
        log_error("compute_token_signal_labels", f"Failed for token_id={token_id}")

    return labels


def compute_token_signal_labels_batch(token_ids: List[int]) -> Dict[int, List[str]]:
    """
    Batch-compute Tier 2 wallet-signal labels for multiple tokens.

    More efficient than calling compute_token_signal_labels() per token
    because it fetches all wallet addresses and tags in two queries.

    Args:
        token_ids: List of token database IDs

    Returns:
        Dict mapping token_id -> list of signal labels
    """
    result: Dict[int, List[str]] = {tid: [] for tid in token_ids}

    if not token_ids:
        return result

    try:
        with sqlite3.connect(settings.DATABASE_FILE) as conn:
            # Get all early buyer wallets for these tokens
            placeholders = ",".join("?" * len(token_ids))
            cursor = conn.execute(
                f"SELECT token_id, wallet_address FROM early_buyer_wallets WHERE token_id IN ({placeholders})",
                token_ids,
            )
            rows = cursor.fetchall()

            if not rows:
                return result

            # Build token -> wallets mapping and collect unique addresses
            wallets_by_token: Dict[int, List[str]] = {tid: [] for tid in token_ids}
            all_addresses: set = set()
            for token_id_val, addr in rows:
                if addr not in wallets_by_token.get(token_id_val, []):
                    wallets_by_token.setdefault(token_id_val, []).append(addr)
                all_addresses.add(addr)

            # Fetch all wallet tags in one query
            addr_list = list(all_addresses)
            addr_placeholders = ",".join("?" * len(addr_list))
            cursor = conn.execute(
                f"SELECT wallet_address, tag FROM wallet_tags WHERE wallet_address IN ({addr_placeholders})",
                addr_list,
            )

            tags_by_wallet: Dict[str, set] = {addr: set() for addr in all_addresses}
            for row in cursor.fetchall():
                addr, tag = row[0], row[1]
                if addr in tags_by_wallet:
                    tags_by_wallet[addr].add(tag)

            # Evaluate signal labels per token
            for tid in token_ids:
                wallet_addrs = wallets_by_token.get(tid, [])
                if not wallet_addrs:
                    continue

                total_wallets = len(wallet_addrs)
                smart_money_count = 0
                cluster_count = 0
                insider_found = False
                whale_found = False
                bot_count = 0

                for addr in wallet_addrs:
                    tags = tags_by_wallet.get(addr, set())

                    if "Consistent Winner" in tags or "High SOL Balance" in tags:
                        smart_money_count += 1
                    if "Cluster" in tags:
                        cluster_count += 1
                    if "Insider" in tags or "KOL" in tags:
                        insider_found = True
                    if "High SOL Balance" in tags:
                        whale_found = True
                    if "Low Value" in tags or "Cluster" in tags:
                        bot_count += 1

                tid_labels: List[str] = []
                if smart_money_count >= 3:
                    tid_labels.append("signal:Smart-Money")
                if cluster_count >= 3:
                    tid_labels.append("signal:Cluster-Alert")
                if insider_found:
                    tid_labels.append("signal:Insider-Heavy")
                if total_wallets > 0 and (bot_count / total_wallets) >= 0.5:
                    tid_labels.append("signal:Bot-Heavy")
                if whale_found:
                    tid_labels.append("signal:Whale-Backed")

                result[tid] = tid_labels

    except Exception:
        log_error("compute_token_signal_labels_batch", f"Failed for {len(token_ids)} tokens")

    return result


def compute_refresh_schedule(
    token_dict: Dict[str, Any],
    swab_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute position-driven refresh schedule fields for a token.

    Returns dict with:
    - is_fast_lane: bool - whether token gets fast-lane refresh
    - next_refresh_at: str | None - ISO timestamp of next scheduled refresh

    Fast-lane criteria (any of):
    - Has open tracked positions
    - Has active webhook
    - Market cap >= tracking_mc_threshold
    """
    ingest_settings = CURRENT_INGEST_SETTINGS
    mc_threshold = ingest_settings.get("tracking_mc_threshold", 100000)
    fast_interval = ingest_settings.get("fast_lane_interval_minutes", 30)
    slow_interval = ingest_settings.get("slow_lane_interval_minutes", 240)

    # Determine fast-lane eligibility
    open_positions = swab_data.get("open_positions", 0)
    webhook_active = bool(token_dict.get("webhook_id"))
    current_mc = token_dict.get("market_cap_usd_current") or token_dict.get("market_cap_usd")
    high_mc = current_mc is not None and current_mc >= mc_threshold

    is_fast_lane = open_positions > 0 or webhook_active or high_mc

    # Calculate next refresh time
    next_refresh_at = None
    market_cap_updated_at = token_dict.get("market_cap_updated_at")

    if market_cap_updated_at:
        try:
            # Parse the last refresh timestamp
            updated = datetime.fromisoformat(market_cap_updated_at.replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)

            # Add appropriate interval
            interval_minutes = fast_interval if is_fast_lane else slow_interval
            next_refresh = updated + timedelta(minutes=interval_minutes)
            next_refresh_at = next_refresh.isoformat()
        except (ValueError, TypeError):
            pass

    return {
        "is_fast_lane": is_fast_lane,
        "next_refresh_at": next_refresh_at,
    }


@router.get("/api/tokens/history", response_model=TokensResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_tokens_history(
    request: Request,
    response: Response,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    dex_id: Optional[str] = None,
    verdict: Optional[str] = None,
    performance: Optional[str] = None,
    since_hours: Optional[int] = None,
):
    """Get non-deleted tokens with wallet counts, server-side pagination and filtering."""
    cache_key = f"tokens_history_{limit}_{offset}_{search}_{dex_id}_{verdict}_{performance}_{since_hours}"

    # Check cache first
    cached_data, cached_etag = cache.get(cache_key)
    if cached_data:
        if_none_match = request.headers.get("if-none-match")
        if if_none_match and if_none_match == cached_etag:
            response.status_code = 304
            return Response(status_code=304)
        response.headers["ETag"] = cached_etag
        return cached_data

    # Fetch from database
    async def fetch_tokens():
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row

            # Build WHERE conditions
            conditions = ["(t.deleted_at IS NULL OR t.deleted_at = '')"]
            params: list = []

            if search:
                conditions.append("(t.token_name LIKE ? OR t.token_symbol LIKE ? OR t.token_address LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

            if dex_id:
                conditions.append("t.dex_id = ?")
                params.append(dex_id)

            if since_hours:
                conditions.append("t.analysis_timestamp >= datetime('now', ?)")
                params.append(f"-{since_hours} hours")

            where_clause = " AND ".join(conditions)

            # Get total count first (for pagination metadata)
            count_query = f"SELECT COUNT(*) FROM analyzed_tokens t WHERE {where_clause}"
            count_cursor = await conn.execute(count_query, params)
            total_count = (await count_cursor.fetchone())[0]

            query = f"""
                SELECT
                    t.id,
                    t.token_address,
                    t.token_name,
                    t.token_symbol,
                    t.acronym,
                    t.analysis_timestamp,
                    t.first_buy_timestamp,
                    t.market_cap_usd,
                    t.market_cap_usd_current,
                    t.market_cap_usd_previous,
                    t.market_cap_updated_at,
                    t.market_cap_ath,
                    t.market_cap_ath_timestamp,
                    {LIQUIDITY_SELECT_EXPR},
                    COUNT(DISTINCT ebw.wallet_address) as wallets_found,
                    t.credits_used, t.last_analysis_credits,
                    (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = t.id AND tt.tag IN ('verified-win', 'verified-loss') ORDER BY tt.tier DESC LIMIT 1) AS verdict,
                    COALESCE(t.state_version, 0) as state_version,
                    t.top_holders_json,
                    t.top_holders_updated_at,
                    t.ingest_source,
                    t.webhook_id,
                    t.dex_id,
                    t.is_cashback
                FROM analyzed_tokens t
                LEFT JOIN early_buyer_wallets ebw ON ebw.token_id = t.id
                WHERE {where_clause}
                GROUP BY t.id
                ORDER BY t.analysis_timestamp DESC
                LIMIT ? OFFSET ?
            """
            cursor = await conn.execute(query, params + [limit, offset])
            rows = await cursor.fetchall()

            # Fetch all token tags in one query
            tag_cursor = await conn.execute(
                "SELECT token_id, tag FROM token_tags WHERE token_id IN ({})".format(
                    ",".join(str(dict(row)["id"]) for row in rows)
                )
                if rows
                else "SELECT token_id, tag FROM token_tags WHERE 0=1"
            )
            tag_rows = await tag_cursor.fetchall()

            # Group tags by token_id
            tags_by_token = {}
            for tag_row in tag_rows:
                token_id = tag_row[0]
                tag = tag_row[1]
                if token_id not in tags_by_token:
                    tags_by_token[token_id] = []
                tags_by_token[token_id].append(tag)

            # Get token IDs for position aggregation
            token_ids = [dict(row)["id"] for row in rows]

            # Fetch position aggregates and Tier 2 signal labels in parallel threads
            swab_aggregates, signal_labels_map = await asyncio.gather(
                asyncio.to_thread(db.get_swab_aggregates_by_token, token_ids),
                asyncio.to_thread(compute_token_signal_labels_batch, token_ids),
            )

            tokens = []
            total_wallets = 0
            for row in rows:
                token_dict = dict(row)
                token_id = token_dict["id"]
                manual_tags = tags_by_token.get(token_id, [])
                token_dict["tags"] = manual_tags

                # Parse top holders JSON
                top_holders_json = token_dict.get("top_holders_json")
                token_dict["top_holders"] = json.loads(top_holders_json) if top_holders_json else None

                # Add position aggregates
                swab_data = swab_aggregates.get(token_id, {})
                token_dict["swab_open_positions"] = swab_data.get("open_positions", 0)
                token_dict["swab_open_pnl_usd"] = swab_data.get("open_pnl_usd")
                token_dict["swab_realized_pnl_usd"] = swab_data.get("realized_pnl_usd")
                token_dict["swab_last_check_at"] = swab_data.get("last_check_at")
                token_dict["swab_webhook_active"] = bool(token_dict.get("webhook_id"))

                # Compute labels (Tier 1 + Tier 2 signal + Tier 3 manual)
                signal_labels = signal_labels_map.get(token_id, [])
                token_dict["labels"] = compute_token_labels(token_dict, swab_data, manual_tags, signal_labels)

                # Compute refresh schedule (is_fast_lane, next_refresh_at)
                refresh_schedule = compute_refresh_schedule(token_dict, swab_data)
                token_dict["is_fast_lane"] = refresh_schedule["is_fast_lane"]
                token_dict["next_refresh_at"] = refresh_schedule["next_refresh_at"]

                tokens.append(token_dict)
                total_wallets += token_dict.get("wallets_found", 0)

            return {"total": total_count, "total_wallets": total_wallets, "tokens": tokens}

    result = await cache.deduplicate_request(cache_key, fetch_tokens)
    etag = cache.set(cache_key, result)
    response.headers["ETag"] = etag
    return result


@router.get("/api/tokens/trash", response_model=TokensResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_deleted_tokens(request: Request):
    """Get all soft-deleted tokens"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        query = """
            SELECT
                t.*,
                COUNT(DISTINCT ebw.wallet_address) as wallets_found
            FROM analyzed_tokens t
            LEFT JOIN early_buyer_wallets ebw ON ebw.token_id = t.id
            WHERE t.deleted_at IS NOT NULL
            GROUP BY t.id
            ORDER BY t.deleted_at DESC
        """
        cursor = await conn.execute(query)
        rows = await cursor.fetchall()

        # Fetch all token tags
        if rows:
            tag_cursor = await conn.execute(
                "SELECT token_id, tag FROM token_tags WHERE token_id IN ({})".format(
                    ",".join(str(dict(row)["id"]) for row in rows)
                )
            )
            tag_rows = await tag_cursor.fetchall()
            tags_by_token = {}
            for tag_row in tag_rows:
                token_id, tag = tag_row[0], tag_row[1]
                if token_id not in tags_by_token:
                    tags_by_token[token_id] = []
                tags_by_token[token_id].append(tag)
        else:
            tags_by_token = {}

        # Get token IDs for position aggregation and signal labels
        token_ids = [dict(row)["id"] for row in rows]
        if token_ids:
            swab_aggregates, signal_labels_map = await asyncio.gather(
                asyncio.to_thread(db.get_swab_aggregates_by_token, token_ids),
                asyncio.to_thread(compute_token_signal_labels_batch, token_ids),
            )
        else:
            swab_aggregates, signal_labels_map = {}, {}

        tokens = []
        for row in rows:
            token_dict = dict(row)
            token_id = token_dict["id"]
            manual_tags = tags_by_token.get(token_id, [])
            token_dict["tags"] = manual_tags

            # Parse top holders JSON
            top_holders_json = token_dict.get("top_holders_json")
            token_dict["top_holders"] = json.loads(top_holders_json) if top_holders_json else None

            # Add position aggregates
            swab_data = swab_aggregates.get(token_id, {})
            token_dict["swab_open_positions"] = swab_data.get("open_positions", 0)
            token_dict["swab_open_pnl_usd"] = swab_data.get("open_pnl_usd")
            token_dict["swab_realized_pnl_usd"] = swab_data.get("realized_pnl_usd")
            token_dict["swab_last_check_at"] = swab_data.get("last_check_at")
            token_dict["swab_webhook_active"] = bool(token_dict.get("webhook_id"))

            # Compute labels (Tier 1 + Tier 2 signal + Tier 3 manual)
            signal_labels = signal_labels_map.get(token_id, [])
            token_dict["labels"] = compute_token_labels(token_dict, swab_data, manual_tags, signal_labels)

            # Compute refresh schedule (is_fast_lane, next_refresh_at)
            refresh_schedule = compute_refresh_schedule(token_dict, swab_data)
            token_dict["is_fast_lane"] = refresh_schedule["is_fast_lane"]
            token_dict["next_refresh_at"] = refresh_schedule["next_refresh_at"]

            tokens.append(token_dict)

        return {"total": len(tokens), "total_wallets": sum(t.get("wallets_found", 0) for t in tokens), "tokens": tokens}


@router.post("/api/tokens/refresh-market-caps", response_model=RefreshMarketCapsResponse)
@conditional_rate_limit(MARKET_CAP_RATE_LIMIT)
async def refresh_market_caps(request: Request, data: RefreshMarketCapsRequest):
    """Refresh current market cap for multiple tokens"""
    from meridinate.settings import HELIUS_API_KEY

    helius = HeliusAPI(HELIUS_API_KEY)
    results = []
    total_credits = 0

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        for token_id in data.token_ids:
            try:
                # Get token address
                cursor = await conn.execute("SELECT token_address FROM analyzed_tokens WHERE id = ?", (token_id,))
                row = await cursor.fetchone()

                if not row:
                    results.append(
                        {
                            "token_id": token_id,
                            "market_cap_usd_current": None,
                            "market_cap_usd_previous": None,
                            "market_cap_updated_at": None,
                            "market_cap_ath": None,
                            "market_cap_ath_timestamp": None,
                            "success": False,
                        }
                    )
                    continue

                token_address = row["token_address"]

                # Get current highest observed market cap and original analysis market cap from database
                cursor = await conn.execute(
                    "SELECT market_cap_ath, market_cap_usd FROM analyzed_tokens WHERE id = ?",
                    (token_id,),
                )
                ath_row = await cursor.fetchone()
                current_ath = ath_row["market_cap_ath"] if ath_row else None
                original_market_cap = ath_row["market_cap_usd"] if ath_row else None

                # Fetch current market cap (DexScreener primary, Helius fallback)
                market_cap_usd, credits = helius.get_market_cap_with_fallback(token_address)
                total_credits += credits

                # Track highest observed: compare current, stored ATH, and original analysis market cap
                # The highest should be the maximum of all three values
                market_cap_ath = current_ath
                ath_timestamp = None

                # Determine the true highest value considering all sources
                candidates = [v for v in [current_ath, original_market_cap, market_cap_usd] if v is not None and v > 0]
                if candidates:
                    true_highest = max(candidates)

                    # Update if the true highest is different from current stored ATH
                    if current_ath is None or true_highest > current_ath:
                        from datetime import datetime, timezone

                        # Determine which value is the new peak
                        if market_cap_usd is not None and market_cap_usd == true_highest:
                            # Current market cap is the new peak
                            market_cap_ath = market_cap_usd
                            ath_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                            previous_value = current_ath if current_ath is not None else 0
                            log_info(
                                f"[Peak MC] New peak for token {token_id}: ${market_cap_ath:,.2f} (previous: ${previous_value:,.2f})"
                            )
                        elif original_market_cap is not None and original_market_cap == true_highest:
                            # Original analysis market cap is the highest
                            market_cap_ath = original_market_cap
                            # Use analysis timestamp
                            cursor = await conn.execute(
                                "SELECT analysis_timestamp FROM analyzed_tokens WHERE id = ?",
                                (token_id,),
                            )
                            analysis_row = await cursor.fetchone()
                            if analysis_row:
                                ath_timestamp = analysis_row["analysis_timestamp"]
                                previous_value = current_ath if current_ath is not None else 0
                                log_info(
                                    f"[Peak MC] Updating peak from analysis for token {token_id}: ${market_cap_ath:,.2f} (previous: ${previous_value:,.2f})"
                                )

                # Update database with current market cap and highest observed
                if ath_timestamp is not None:
                    # New peak reached - update both current and highest
                    await conn.execute(
                        """
                        UPDATE analyzed_tokens
                        SET market_cap_usd_previous = market_cap_usd_current,
                            market_cap_usd_current = ?,
                            market_cap_ath = ?,
                            market_cap_ath_timestamp = ?,
                            market_cap_updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (market_cap_usd, market_cap_ath, ath_timestamp, token_id),
                    )
                    log_info(f"[Database] New peak market cap for token {token_id}: ${market_cap_ath:,.2f}")
                else:
                    # No new peak - only update current market cap
                    await conn.execute(
                        """
                        UPDATE analyzed_tokens
                        SET market_cap_usd_previous = market_cap_usd_current,
                            market_cap_usd_current = ?,
                            market_cap_updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (market_cap_usd, token_id),
                    )

                await conn.commit()
                log_info(
                    f"[Database] Updated market cap for token {token_id}: ${market_cap_usd:,.2f}"
                    if market_cap_usd
                    else f"[Database] Updated market cap for token {token_id}: N/A"
                )

                # Get the updated timestamp, peak data, and previous value
                cursor = await conn.execute(
                    "SELECT market_cap_updated_at, market_cap_ath, market_cap_ath_timestamp, market_cap_usd_previous, analysis_timestamp FROM analyzed_tokens WHERE id = ?",
                    (token_id,),
                )
                updated_row = await cursor.fetchone()
                market_cap_updated_at = updated_row["market_cap_updated_at"] if updated_row else None
                market_cap_ath_db = updated_row["market_cap_ath"] if updated_row else None
                ath_timestamp_db = updated_row["market_cap_ath_timestamp"] if updated_row else None
                market_cap_usd_previous = updated_row["market_cap_usd_previous"] if updated_row else None
                analysis_ts = updated_row["analysis_timestamp"] if updated_row else None

                # Compute auto-verdict based on MC performance
                if original_market_cap and original_market_cap > 0:
                    try:
                        auto_verdict = await compute_auto_verdict(
                            conn,
                            token_id,
                            original_market_cap,
                            market_cap_usd,
                            market_cap_ath_db,
                            analysis_ts,
                        )
                        if auto_verdict:
                            await conn.commit()
                    except Exception as verdict_err:
                        log_error(f"[AutoVerdict] Error computing verdict for token {token_id}: {verdict_err}")

                results.append(
                    {
                        "token_id": token_id,
                        "market_cap_usd_current": market_cap_usd,
                        "market_cap_usd_previous": market_cap_usd_previous,
                        "market_cap_updated_at": market_cap_updated_at,
                        "market_cap_ath": market_cap_ath_db,
                        "market_cap_ath_timestamp": ath_timestamp_db,
                        "success": True,
                    }
                )

            except Exception as e:
                log_error(f"Failed to refresh market cap for token {token_id}: {e}")
                results.append(
                    {
                        "token_id": token_id,
                        "market_cap_usd_current": None,
                        "market_cap_usd_previous": None,
                        "market_cap_updated_at": None,
                        "market_cap_ath": None,
                        "market_cap_ath_timestamp": None,
                        "success": False,
                    }
                )

    successful = sum(1 for r in results if r["success"])
    # Invalidate the cached tokens history so the frontend sees fresh market caps
    cache.invalidate("tokens_history")

    # Record batch market cap refresh credits
    if total_credits > 0:
        credit_tracker.record_batch(
            CreditOperation.MARKET_CAP_REFRESH,
            credits=total_credits,
            count=len(data.token_ids),
            context={"successful": successful, "token_ids": data.token_ids},
        )
        # Log to operation log for credits panel
        get_credit_tracker().record_operation(
            operation="mc_refresh",
            label="Market Cap Refresh",
            credits=total_credits,
            call_count=len(data.token_ids),
            context={"successful": successful},
        )

    return {
        "message": f"Refreshed {successful}/{len(data.token_ids)} token market caps",
        "results": results,
        "total_tokens": len(data.token_ids),
        "successful": successful,
        "api_credits_used": total_credits,
    }


@router.get("/api/tokens/{token_id}", response_model=TokenDetail)
async def get_token_by_id(token_id: int, include_axiom: bool = False):
    """Get token details with wallets. Axiom JSON excluded by default for performance."""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        # Get column names excluding axiom_json (large blob, loaded separately if needed)
        pragma_cursor = await conn.execute("PRAGMA table_info(analyzed_tokens)")
        all_cols = [row[1] for row in await pragma_cursor.fetchall() if row[1] != "axiom_json"]
        col_list = ", ".join(all_cols)

        token_query = f"""
            SELECT {col_list} FROM analyzed_tokens
            WHERE id = ? AND (deleted_at IS NULL OR deleted_at = '')
        """
        cursor = await conn.execute(token_query, (token_id,))
        token_row = await cursor.fetchone()

        if not token_row:
            raise HTTPException(status_code=404, detail="Token not found")

        token = dict(zip(all_cols, token_row))

        # Get wallets for this token with position status
        wallets_query = """
            SELECT ebw.*,
                   mtp.still_holding,
                   mtp.realized_pnl,
                   mtp.pnl_source
            FROM early_buyer_wallets ebw
            LEFT JOIN mtew_token_positions mtp
                ON mtp.wallet_address = ebw.wallet_address AND mtp.token_id = ebw.token_id
            WHERE ebw.token_id = ?
            ORDER BY ebw.first_buy_timestamp ASC
        """
        cursor = await conn.execute(wallets_query, (token_id,))
        wallet_rows = await cursor.fetchall()
        token["wallets"] = [dict(row) for row in wallet_rows]

        # Only load axiom_json if explicitly requested (for download)
        if include_axiom:
            axiom_query = "SELECT axiom_json FROM analyzed_tokens WHERE id = ?"
            cursor = await conn.execute(axiom_query, (token_id,))
            axiom_row = await cursor.fetchone()
            token["axiom_json"] = json.loads(axiom_row[0]) if axiom_row and axiom_row[0] else []
        else:
            token["axiom_json"] = []

        # Get token tags
        tags_query = "SELECT tag FROM token_tags WHERE token_id = ?"
        cursor = await conn.execute(tags_query, (token_id,))
        tag_rows = await cursor.fetchall()
        manual_tags = [row[0] for row in tag_rows]
        token["tags"] = manual_tags

        # Parse top holders JSON
        top_holders_json = token.get("top_holders_json")
        token["top_holders"] = json.loads(top_holders_json) if top_holders_json else None

        # Add position aggregates and Tier 2 signal labels (parallel)
        swab_future, signal_future = await asyncio.gather(
            asyncio.to_thread(db.get_swab_aggregates_by_token, [token_id]),
            asyncio.to_thread(compute_token_signal_labels, token_id),
        )
        swab_data = swab_future.get(token_id, {})
        signal_labels = signal_future
        token["swab_open_positions"] = swab_data.get("open_positions", 0)
        token["swab_open_pnl_usd"] = swab_data.get("open_pnl_usd")
        token["swab_realized_pnl_usd"] = swab_data.get("realized_pnl_usd")
        token["swab_last_check_at"] = swab_data.get("last_check_at")
        token["swab_webhook_active"] = bool(token.get("webhook_id"))

        # Compute labels (Tier 1 + Tier 2 signal + Tier 3 manual)
        token["labels"] = compute_token_labels(token, swab_data, manual_tags, signal_labels)

        # Compute refresh schedule (is_fast_lane, next_refresh_at)
        refresh_schedule = compute_refresh_schedule(token, swab_data)
        token["is_fast_lane"] = refresh_schedule["is_fast_lane"]
        token["next_refresh_at"] = refresh_schedule["next_refresh_at"]

        return token


@router.get("/api/tokens/{token_id}/history", response_model=AnalysisHistory)
async def get_token_analysis_history(token_id: int):
    """Get analysis history for a specific token"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        # Verify token exists
        token_query = "SELECT id FROM analyzed_tokens WHERE id = ?"
        cursor = await conn.execute(token_query, (token_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Token not found")

        # Fetch analysis runs
        runs_query = """
            SELECT id, analysis_timestamp, wallets_found, credits_used
            FROM analysis_runs
            WHERE token_id = ?
            ORDER BY analysis_timestamp DESC
        """
        cursor = await conn.execute(runs_query, (token_id,))
        run_rows = await cursor.fetchall()

        runs = []
        for run_row in run_rows:
            run = dict(run_row)
            wallets_query = """
                SELECT *
                FROM early_buyer_wallets
                WHERE analysis_run_id = ?
                ORDER BY position ASC
            """
            wallet_cursor = await conn.execute(wallets_query, (run["id"],))
            wallet_rows = await wallet_cursor.fetchall()
            run["wallets"] = [dict(w) for w in wallet_rows]
            runs.append(run)

        return {"token_id": token_id, "total_runs": len(runs), "runs": runs}


@router.delete("/api/tokens/{token_id}", response_model=MessageResponse)
async def soft_delete_token(token_id: int):
    """Soft delete a token (move to trash)"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        query = "UPDATE analyzed_tokens SET deleted_at = ? WHERE id = ?"
        await conn.execute(query, (datetime.utcnow().isoformat(), token_id))
        await conn.commit()

    cache.invalidate("tokens_history")
    return {"message": "Token moved to trash"}


@router.post("/api/tokens/{token_id}/restore", response_model=MessageResponse)
async def restore_token(token_id: int):
    """Restore a soft-deleted token"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        query = "UPDATE analyzed_tokens SET deleted_at = NULL WHERE id = ?"
        await conn.execute(query, (token_id,))
        await conn.commit()

    cache.invalidate("tokens_history")
    return {"message": "Token restored"}


@router.delete("/api/tokens/{token_id}/permanent", response_model=MessageResponse)
async def permanent_delete_token(token_id: int):
    """Permanently delete a token and all associated data"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        # Delete in order: wallets, analysis runs, token
        await conn.execute("DELETE FROM early_buyer_wallets WHERE token_id = ?", (token_id,))
        await conn.execute("DELETE FROM analysis_runs WHERE token_id = ?", (token_id,))
        await conn.execute("DELETE FROM analyzed_tokens WHERE id = ?", (token_id,))
        await conn.commit()

    cache.invalidate("tokens_history")
    return {"message": "Token permanently deleted"}


@router.post("/api/tokens/{token_id}/verdict", response_model=MessageResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def update_verdict(token_id: int, request: Request, data: UpdateVerdictRequest):
    """Update the verdict of a token (verified-win, verified-loss, or null to clear)"""
    verdict = data.verdict

    # Backward-compatible mapping: accept old names during transition
    _VERDICT_MAP = {"gem": "verified-win", "dud": "verified-loss"}
    if verdict in _VERDICT_MAP:
        verdict = _VERDICT_MAP[verdict]

    # Validate verdict value
    if verdict is not None and verdict not in ["verified-win", "verified-loss"]:
        raise HTTPException(status_code=400, detail="verdict must be 'verified-win', 'verified-loss', or null")

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        # Remove any existing verdict tags (both manual and auto)
        await conn.execute(
            "DELETE FROM token_tags WHERE token_id = ? AND tag IN ('verified-win', 'verified-loss')",
            (token_id,),
        )
        # Insert new manual verdict tag if provided
        if verdict is not None:
            await conn.execute(
                "INSERT INTO token_tags (token_id, tag, tier, source, updated_at) VALUES (?, ?, 3, 'manual', CURRENT_TIMESTAMP)",
                (token_id, verdict),
            )
        # NULL out gem_status for cleanup
        await conn.execute("UPDATE analyzed_tokens SET gem_status = NULL WHERE id = ?", (token_id,))
        await conn.commit()

    # Invalidate both tokens cache and multi-token wallets cache
    cache.invalidate("tokens_history")
    cache.invalidate("multi_early_buyer_wallets")

    status_msg = "cleared" if verdict is None else f"set to {verdict}"
    return {"message": f"Token verdict {status_msg}"}


@router.post("/api/tokens/{token_id}/rug-label")
async def set_rug_label(token_id: int, request: Request):
    """Set manual rug label on a token (rug, organic, unsure, or null to clear)."""
    body = await request.json()
    label = body.get("label")

    if label is not None and label not in ("fake", "real", "unsure"):
        raise HTTPException(status_code=400, detail="label must be 'rug', 'organic', 'unsure', or null")

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        if label:
            await conn.execute(
                "UPDATE analyzed_tokens SET rug_label = ?, rug_label_at = CURRENT_TIMESTAMP WHERE id = ?",
                (label, token_id),
            )
        else:
            await conn.execute(
                "UPDATE analyzed_tokens SET rug_label = NULL, rug_label_at = NULL WHERE id = ?",
                (token_id,),
            )
        await conn.commit()

    cache.invalidate("tokens_history")
    return {"message": f"Rug label {'cleared' if not label else f'set to {label}'}"}


@router.get("/api/tokens/rug-labels")
async def get_rug_labeled_tokens():
    """Get all tokens with rug labels (for rug analysis page)."""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT id, token_address, token_name, token_symbol, market_cap_usd,
                   market_cap_usd_current, liquidity_usd, rug_label, rug_label_at,
                   deployer_address, clobr_score, lp_trust_score,
                   fresh_wallet_pct, bundle_cluster_count, stealth_holder_count
            FROM analyzed_tokens
            WHERE rug_label IS NOT NULL AND (deleted_at IS NULL OR deleted_at = '')
            ORDER BY rug_label_at DESC
        """)
        rows = [dict(r) for r in await cursor.fetchall()]
    return {"tokens": rows, "count": len(rows)}


# ============================================================================
# Token Tags Endpoints
# ============================================================================


@router.get("/api/tokens/{token_id}/tags", response_model=TokenTagsResponse)
async def get_token_tags(token_id: int):
    """Get tags for a token"""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        query = "SELECT tag FROM token_tags WHERE token_id = ?"
        cursor = await conn.execute(query, (token_id,))
        rows = await cursor.fetchall()
        tags = [row[0] for row in rows]
        return {"tags": tags}


@router.post("/api/tokens/{token_id}/tags", response_model=MessageResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def add_token_tag(token_id: int, request: Request, data: TokenTagRequest):
    """Add a tag to a token (e.g., verified-win, verified-loss)"""
    # Backward-compatible mapping: accept old names during transition
    _TAG_MAP = {"gem": "verified-win", "dud": "verified-loss"}
    tag = _TAG_MAP.get(data.tag, data.tag)

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        try:
            await conn.execute(
                "INSERT INTO token_tags (token_id, tag) VALUES (?, ?)",
                (token_id, tag),
            )
            await conn.commit()
            log_info("Token tag added", token_id=token_id, tag=tag)
        except aiosqlite.IntegrityError:
            log_error("Failed to add token tag - tag already exists", token_id=token_id, tag=tag)
            raise HTTPException(status_code=400, detail="Tag already exists for this token")

    # Invalidate caches
    cache.invalidate("tokens_history")
    cache.invalidate("multi_early_buyer_wallets")

    return {"message": f"Tag '{tag}' added successfully"}


@router.delete("/api/tokens/{token_id}/tags", response_model=MessageResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def remove_token_tag(token_id: int, request: Request, data: TokenTagRequest):
    """Remove a tag from a token"""
    # Backward-compatible mapping: accept old names during transition
    _TAG_MAP = {"gem": "verified-win", "dud": "verified-loss"}
    tag = _TAG_MAP.get(data.tag, data.tag)

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        await conn.execute("DELETE FROM token_tags WHERE token_id = ? AND tag = ?", (token_id, tag))
        await conn.commit()
        log_info("Token tag removed", token_id=token_id, tag=tag)

    # Invalidate caches
    cache.invalidate("tokens_history")
    cache.invalidate("multi_early_buyer_wallets")

    return {"message": f"Tag '{tag}' removed successfully"}


@router.get("/api/tokens/{mint_address}/top-holders", response_model=TopHoldersResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_top_holders(mint_address: str, request: Request, limit: int = None):
    """
    Get top N token holders for a given token mint address.

    This endpoint:
    1. Calls Helius getTokenLargestAccounts API (1 credit)
    2. Returns top N holders with their balances
    3. Updates token's cumulative API credits if token exists in DB

    Args:
        mint_address: Token mint address to analyze
        limit: Number of top holders to return (default: from settings, range: 5-20)

    Returns:
        TopHoldersResponse with holder addresses and balances
    """
    try:
        # Get limit from settings if not provided
        if limit is None:
            api_settings = get_api_settings()
            limit = api_settings.topHoldersLimit

        # Validate limit range (aligned with Helius API cap and frontend)
        if limit < 5 or limit > 20:
            raise HTTPException(status_code=400, detail="Limit must be between 5 and 20")

        # Initialize Helius API with separate Top Holders API key
        from meridinate.settings import HELIUS_TOP_HOLDERS_API_KEY

        helius = HeliusAPI(HELIUS_TOP_HOLDERS_API_KEY)

        # Fetch top holders
        log_info("Fetching top holders", mint_address=mint_address[:8], limit=limit)
        holders_data, credits_used = helius.get_top_holders(mint_address, limit=limit)

        if not holders_data:
            log_error("No holders found", mint_address=mint_address[:8])
            raise HTTPException(status_code=404, detail="No holders found for this token")

        # Fetch token metadata to get symbol
        token_symbol = None
        try:
            token_metadata, metadata_credits = helius.get_token_metadata(mint_address)
            credits_used += metadata_credits
            if token_metadata:
                # Extract symbol from onChainMetadata
                on_chain = token_metadata.get("onChainMetadata", {})
                metadata = on_chain.get("metadata", {})
                token_symbol = metadata.get("symbol", "TOKEN")
        except Exception as e:
            log_error(f"Failed to fetch token metadata: {str(e)}", mint_address=mint_address[:8])
            token_symbol = "TOKEN"  # Fallback

        # Fetch wallet balances in USD for each holder
        for holder in holders_data:
            try:
                wallet_balance_usd, balance_credits = helius.get_wallet_balance(holder["address"])
                holder["wallet_balance_usd"] = wallet_balance_usd
                credits_used += balance_credits
            except Exception as e:
                log_error(f"Failed to fetch wallet balance for {holder['address'][:8]}: {str(e)}")
                holder["wallet_balance_usd"] = None

        # Update API credits for this token if it exists in database
        try:
            async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
                # Check if token exists
                cursor = await conn.execute(
                    "SELECT id, credits_used FROM analyzed_tokens WHERE token_address = ?", (mint_address,)
                )
                row = await cursor.fetchone()

                if row:
                    token_id, current_credits = row
                    new_credits = (current_credits or 0) + credits_used

                    # Prepare top holders JSON for storage
                    top_holders_json = json.dumps(holders_data)

                    # Update cumulative credits and top holders data
                    await conn.execute(
                        """UPDATE analyzed_tokens
                        SET credits_used = ?,
                            last_analysis_credits = ?,
                            top_holders_json = ?,
                            top_holders_updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?""",
                        (new_credits, credits_used, top_holders_json, token_id),
                    )
                    await conn.commit()
                    log_info(
                        "Updated token credits and top holders data",
                        token_id=token_id,
                        credits_added=credits_used,
                        total_credits=new_credits,
                        holders_count=len(holders_data),
                    )

                    # Invalidate tokens cache to show updated credits
                    cache.invalidate("tokens_history")
        except Exception as db_error:
            # Log database error but don't fail the request
            log_error(f"Failed to update token credits: {str(db_error)}", mint_address=mint_address[:8])

        # Format response
        return TopHoldersResponse(
            token_address=mint_address,
            token_symbol=token_symbol,
            holders=holders_data,
            total_holders=len(holders_data),
            api_credits_used=credits_used,
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log_error(f"Error in get_top_holders: {str(e)}", mint_address=mint_address[:8])
        raise HTTPException(status_code=500, detail=f"Failed to fetch top holders: {str(e)}")


# =============================================================================
# Performance Scoring Endpoints
# =============================================================================


class ScoreTokensRequest(BaseModel):
    """Request model for scoring tokens."""

    token_addresses: Optional[List[str]] = None
    score_all_hot: bool = False


class ScoreTokensResponse(BaseModel):
    """Response model for token scoring."""

    status: str
    tokens_scored: int = 0
    tokens_skipped: int = 0
    by_bucket: Dict[str, int] = {}
    errors: List[str] = []
    message: Optional[str] = None


class PerformanceSnapshotResponse(BaseModel):
    """Response model for a performance snapshot."""

    id: int
    token_address: str
    captured_at: str
    price_usd: Optional[float] = None
    mc_usd: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    liquidity_usd: Optional[float] = None
    holder_count: Optional[int] = None
    top_holder_share: Optional[float] = None
    our_positions_pnl_usd: Optional[float] = None
    lp_locked: Optional[bool] = None
    ingest_tier_snapshot: Optional[str] = None


class TokenPerformanceResponse(BaseModel):
    """Response model for token performance data."""

    token_address: str
    performance_score: Optional[float] = None
    performance_bucket: Optional[str] = None
    score_explanation: Optional[List[Dict]] = None
    score_timestamp: Optional[str] = None
    snapshots: List[PerformanceSnapshotResponse] = []


@router.post("/api/tokens/score", response_model=ScoreTokensResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def score_tokens(request: Request, payload: ScoreTokensRequest):
    """
    Recompute performance scores for tokens.

    Can score specific tokens by address or all hot tokens.

    Args:
        payload: ScoreTokensRequest with token_addresses or score_all_hot flag

    Returns:
        ScoreTokensResponse with scoring results
    """
    from meridinate.tasks.performance_scorer import score_tokens as do_score_tokens
    from meridinate.tasks.performance_scorer import score_all_hot_tokens

    try:
        if payload.score_all_hot:
            result = await score_all_hot_tokens()
        elif payload.token_addresses:
            result = await do_score_tokens(payload.token_addresses)
        else:
            return ScoreTokensResponse(
                status="error",
                message="Provide token_addresses or set score_all_hot=true",
            )

        if result.get("status") == "disabled":
            return ScoreTokensResponse(
                status="disabled",
                message=result.get("message", "Scoring is disabled"),
            )

        return ScoreTokensResponse(
            status="success",
            tokens_scored=result.get("tokens_scored", 0),
            tokens_skipped=result.get("tokens_skipped", 0),
            by_bucket=result.get("by_bucket", {}),
            errors=result.get("errors", []),
        )

    except Exception as e:
        log_error(f"Error scoring tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/tokens/{token_address}/performance", response_model=TokenPerformanceResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_token_performance(
    token_address: str,
    request: Request,
    limit: int = 20,
    since_hours: Optional[float] = None,
):
    """
    Get performance data and snapshots for a token.

    Returns current score, bucket, explanation, and recent snapshots.

    Args:
        token_address: Token address
        limit: Max snapshots to return (default: 20)
        since_hours: Only return snapshots from last N hours

    Returns:
        TokenPerformanceResponse with score and snapshot history
    """
    try:
        # Get token's current score from database
        async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT performance_score, performance_bucket, score_explanation, score_timestamp
                FROM analyzed_tokens
                WHERE token_address = ?
            """,
                (token_address,),
            )
            row = await cursor.fetchone()

        score = None
        bucket = None
        explanation = None
        score_timestamp = None

        if row:
            score = row["performance_score"]
            bucket = row["performance_bucket"]
            score_timestamp = row["score_timestamp"]
            if row["score_explanation"]:
                try:
                    explanation = json.loads(row["score_explanation"])
                except Exception:
                    explanation = None

        # Get snapshots
        snapshots = await asyncio.to_thread(
            db.get_performance_snapshots,
            token_address, limit=limit, since_hours=since_hours
        )

        # Convert snapshots to response models
        snapshot_responses = []
        for snap in snapshots:
            snapshot_responses.append(
                PerformanceSnapshotResponse(
                    id=snap["id"],
                    token_address=snap["token_address"],
                    captured_at=snap["captured_at"],
                    price_usd=snap.get("price_usd"),
                    mc_usd=snap.get("mc_usd"),
                    volume_24h_usd=snap.get("volume_24h_usd"),
                    liquidity_usd=snap.get("liquidity_usd"),
                    holder_count=snap.get("holder_count"),
                    top_holder_share=snap.get("top_holder_share"),
                    our_positions_pnl_usd=snap.get("our_positions_pnl_usd"),
                    lp_locked=bool(snap.get("lp_locked")) if snap.get("lp_locked") is not None else None,
                    ingest_tier_snapshot=snap.get("ingest_tier_snapshot"),
                )
            )

        return TokenPerformanceResponse(
            token_address=token_address,
            performance_score=score,
            performance_bucket=bucket,
            score_explanation=explanation,
            score_timestamp=score_timestamp,
            snapshots=snapshot_responses,
        )

    except Exception as e:
        log_error(f"Error getting token performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class PrimeTokensResponse(BaseModel):
    """Response model for prime tokens ready to promote."""

    count: int
    tokens: List[Dict[str, Any]]


@router.get("/api/tokens/prime-for-promotion", response_model=PrimeTokensResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_prime_tokens_for_promotion(request: Request, limit: int = 10):
    """
    Get Prime-bucket tokens that are ready for promotion.

    These are tokens scored as 'prime' that are still in ingested/enriched tier.

    Args:
        limit: Max tokens to return (default: 10)

    Returns:
        PrimeTokensResponse with list of tokens ready to promote
    """
    try:
        tokens = await asyncio.to_thread(db.get_prime_tokens_for_promotion, limit=limit)
        return PrimeTokensResponse(count=len(tokens), tokens=tokens)
    except Exception as e:
        log_error(f"Error getting prime tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/tokens/backfill-deployers")
async def backfill_deployers(request: Request, max_tokens: int = 50):
    """
    Backfill deployer_address and creation_events for existing tokens that don't have them.
    Re-analyzes the earliest transactions to extract deployer info.
    Costs ~100 Helius credits per token (1 getTransactionsForAddress call).
    """
    from meridinate.settings import HELIUS_API_KEY
    from meridinate.helius_api import HeliusAPI
    from meridinate.tasks.ingest_tasks import tag_deployer_wallet

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT id, token_address, token_name FROM analyzed_tokens "
            "WHERE deployer_address IS NULL AND (deleted_at IS NULL OR deleted_at = '') "
            "ORDER BY analysis_timestamp DESC LIMIT ?",
            (max_tokens,)
        )
        tokens = [dict(r) for r in await cursor.fetchall()]

    if not tokens:
        return {"message": "All tokens already have deployer data", "tokens_updated": 0}

    helius = HeliusAPI(HELIUS_API_KEY)
    updated = 0
    total_credits = 0

    for token in tokens:
        try:
            # Fetch just the first 20 transactions to find deployer
            transactions, credits = await asyncio.to_thread(
                helius.get_parsed_transactions,
                token["token_address"], limit=20, get_earliest=True, max_credits=200
            )
            total_credits += credits

            if not transactions:
                continue

            # Extract deployer from first transaction (largest SOL sender)
            result = {"deployer_address": None, "creation_events": []}
            mint_addr = token["token_address"]

            for tx_idx, tx in enumerate(transactions[:20]):
                if not tx.get("timestamp"):
                    continue
                tx_time = datetime.utcfromtimestamp(tx["timestamp"])
                token_transfers = tx.get("tokenTransfers", [])
                native_transfers = tx.get("nativeTransfers", [])

                # Find largest SOL sender
                largest_sender = None
                largest_amount = 0
                for nt in native_transfers:
                    amt = nt.get("amount", 0)
                    sender = nt.get("fromUserAccount")
                    if sender and amt > largest_amount:
                        largest_amount = amt
                        largest_sender = sender

                # First transaction = token creation
                if tx_idx == 0 and largest_sender:
                    result["deployer_address"] = largest_sender
                    result["creation_events"].append({
                        "type": "CREATE",
                        "timestamp": tx_time.isoformat(),
                        "wallet": largest_sender,
                        "signature": tx.get("signature", ""),
                        "sol_amount": largest_amount / 1e9,
                    })
                    # PumpFun: create + first buy in same tx
                    has_mint_from_none = any(
                        t.get("mint") == mint_addr and not t.get("fromUserAccount")
                        for t in token_transfers
                    )
                    if has_mint_from_none and largest_amount > 100000:
                        result["creation_events"].append({
                            "type": "FIRST_BUY",
                            "timestamp": tx_time.isoformat(),
                            "wallet": largest_sender,
                            "signature": tx.get("signature", ""),
                            "sol_amount": largest_amount / 1e9,
                            "usd_amount": (largest_amount / 1e9) * 200,
                        })
                        break
                    continue

                # Already found first buy
                if any(e["type"] == "FIRST_BUY" for e in result["creation_events"]):
                    break

                has_mint_transfer = any(t.get("mint") == mint_addr for t in token_transfers)
                if not has_mint_transfer or not largest_sender:
                    continue

                if largest_sender == result["deployer_address"] and not any(e["type"] == "ADD_LIQUIDITY" for e in result["creation_events"]):
                    result["creation_events"].append({
                        "type": "ADD_LIQUIDITY",
                        "timestamp": tx_time.isoformat(),
                        "wallet": largest_sender,
                        "signature": tx.get("signature", ""),
                        "sol_amount": largest_amount / 1e9,
                    })
                else:
                    result["creation_events"].append({
                        "type": "FIRST_BUY",
                        "timestamp": tx_time.isoformat(),
                        "wallet": largest_sender,
                        "signature": tx.get("signature", ""),
                        "sol_amount": largest_amount / 1e9,
                        "usd_amount": (largest_amount / 1e9) * 200,
                    })
                    break

            if result["deployer_address"]:
                async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
                    await conn.execute(
                        "UPDATE analyzed_tokens SET deployer_address = ?, creation_events_json = ? WHERE id = ?",
                        (result["deployer_address"], json.dumps(result["creation_events"]), token["id"])
                    )
                    await conn.commit()
                tag_deployer_wallet(result["deployer_address"])
                updated += 1
                log_info(f"[Backfill] {token['token_name']}: deployer={result['deployer_address'][:12]}...")

        except Exception as e:
            log_error(f"[Backfill] Failed for {token['token_name']}: {e}")

    from meridinate.credit_tracker import get_credit_tracker
    get_credit_tracker().record_operation(
        operation="backfill_deployers", label="Backfill Deployers",
        credits=total_credits, call_count=updated,
        context={"tokens_checked": len(tokens), "tokens_updated": updated},
    )

    return {
        "tokens_checked": len(tokens),
        "tokens_updated": updated,
        "credits_used": total_credits,
    }


@router.post("/api/tokens/detect-sniper-bots")
async def detect_sniper_bots_endpoint(request: Request):
    """Run sniper bot detection across all wallets. Tags bots and removes false winner tags."""
    from meridinate.tasks.ingest_tasks import detect_and_tag_sniper_bots
    result = await asyncio.to_thread(detect_and_tag_sniper_bots)
    return result


@router.get("/api/tokens/ml-features")
async def get_ml_features(request: Request, export_csv: bool = False):
    """
    Extract ML feature vectors for all labeled tokens.
    Returns feature data as JSON, or exports to CSV if export_csv=True.
    No API calls — all data from database.
    """
    from meridinate.tasks.feature_extractor import extract_all_features, export_features_csv

    if export_csv:
        output = await asyncio.to_thread(export_features_csv)
        return {"exported": output, "message": f"Features exported to {output}"}

    features = await asyncio.to_thread(extract_all_features)
    return {
        "total": len(features),
        "wins": sum(1 for f in features if f["is_win"] == 1),
        "losses": sum(1 for f in features if f["is_win"] == 0),
        "feature_count": len(features[0]) - 3 if features else 0,  # exclude metadata cols
        "features": features,
    }
