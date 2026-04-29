"""
Leaderboard router - wallet PnL leaderboard and profile endpoints

Provides REST endpoints for wallet leaderboard ranking, individual wallet profiles,
and triggering PnL computation for tracked wallets.
"""

import asyncio
import json
from typing import Any, Dict, List

import aiosqlite
from fastapi import APIRouter, HTTPException, Query, Request

from meridinate import settings
from meridinate.observability import log_error, log_info

router = APIRouter()

ALLOWED_SORT_FIELDS = {
    "total_pnl_usd", "realized_pnl_usd", "unrealized_pnl_usd",
    "pnl_1d_usd", "pnl_7d_usd", "pnl_30d_usd",
    "tokens_traded", "win_rate", "best_trade_pnl", "worst_trade_pnl",
    "avg_entry_seconds", "wallet_balance_usd", "avg_hold_hours_7d",
    "tier_score", "home_runs", "rugs",
}


@router.get("/api/leaderboard")
async def get_wallet_leaderboard(
    request: Request,
    sort_by: str = Query("total_pnl_usd", description="Sort field"),
    sort_dir: str = Query("desc", description="Sort direction"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: str = Query("", description="Search wallet address (full DB)"),
    tags: str = Query("", description="Comma-separated include tags (AND)"),
    exclude_tags: str = Query("", description="Comma-separated exclude tags"),
    include_tiers: str = Query("", description="Comma-separated include tiers (AND)"),
    exclude_tiers: str = Query("", description="Comma-separated exclude tiers"),
    min_home_runs: int = Query(0, ge=0),
    hold_time: str = Query("", description="Hold time filter: <1h, 1-4h, 4-24h, >24h"),
    starred_only: bool = Query(False, description="Show only starred wallets"),
):
    """
    Wallet leaderboard — queries pre-computed cache tables.
    All filters run server-side against the full wallet database.
    Cache is rebuilt after MC tracker and position checker jobs.
    """
    if sort_by not in ALLOWED_SORT_FIELDS:
        raise HTTPException(status_code=400, detail=f"Invalid sort_by. Allowed: {', '.join(sorted(ALLOWED_SORT_FIELDS))}")
    if sort_dir.lower() not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="sort_dir must be 'asc' or 'desc'")

    sort_direction = sort_dir.upper()
    search_query = search.strip().lower()
    tag_filters = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    exclude_tag_filters = [t.strip() for t in exclude_tags.split(",") if t.strip()] if exclude_tags else []
    include_tier_filters = [t.strip() for t in include_tiers.split(",") if t.strip()] if include_tiers else []
    exclude_tier_filters = [t.strip() for t in exclude_tiers.split(",") if t.strip()] if exclude_tiers else []

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        # Build dynamic SQL query against cache tables
        joins = []
        wheres = []
        params: list = []

        # Tag include (AND): wallet must have ALL specified tags
        for i, tag in enumerate(tag_filters):
            alias = f"ti{i}"
            joins.append(f"JOIN wallet_leaderboard_tags {alias} ON {alias}.wallet_address = c.wallet_address AND {alias}.tag = ?")
            params.append(tag)

        # Tag exclude (NOT ANY)
        if exclude_tag_filters:
            ph = ",".join("?" for _ in exclude_tag_filters)
            wheres.append(f"c.wallet_address NOT IN (SELECT wallet_address FROM wallet_leaderboard_tags WHERE tag IN ({ph}))")
            params.extend(exclude_tag_filters)

        # Tier include (AND): wallet must have ALL specified tiers
        for i, tier in enumerate(include_tier_filters):
            alias = f"tr{i}"
            joins.append(f"JOIN wallet_leaderboard_tiers {alias} ON {alias}.wallet_address = c.wallet_address AND {alias}.tier_tag = ?")
            params.append(tier)

        # Tier exclude (NOT ANY)
        if exclude_tier_filters:
            ph = ",".join("?" for _ in exclude_tier_filters)
            wheres.append(f"c.wallet_address NOT IN (SELECT wallet_address FROM wallet_leaderboard_tiers WHERE tier_tag IN ({ph}))")
            params.extend(exclude_tier_filters)

        # Min home runs
        if min_home_runs > 0:
            wheres.append("c.home_runs >= ?")
            params.append(min_home_runs)

        # Starred only
        if starred_only:
            wheres.append("c.wallet_address IN (SELECT item_address FROM starred_items WHERE item_type = 'wallet')")

        # Hold time range
        if hold_time == "<1h":
            wheres.append("c.avg_hold_hours_7d IS NOT NULL AND c.avg_hold_hours_7d < 1")
        elif hold_time == "1-4h":
            wheres.append("c.avg_hold_hours_7d IS NOT NULL AND c.avg_hold_hours_7d >= 1 AND c.avg_hold_hours_7d < 4")
        elif hold_time == "4-24h":
            wheres.append("c.avg_hold_hours_7d IS NOT NULL AND c.avg_hold_hours_7d >= 4 AND c.avg_hold_hours_7d < 24")
        elif hold_time == ">24h":
            wheres.append("c.avg_hold_hours_7d IS NOT NULL AND c.avg_hold_hours_7d >= 24")

        # Search
        is_search = bool(search_query)
        if is_search:
            wheres.append("c.wallet_address LIKE ?")
            params.append(f"%{search_query}%")

        join_sql = " ".join(joins)
        where_sql = (" WHERE " + " AND ".join(wheres)) if wheres else ""

        # Total count
        count_sql = f"SELECT COUNT(DISTINCT c.wallet_address) FROM wallet_leaderboard_cache c {join_sql}{where_sql}"
        cursor = await conn.execute(count_sql, params)
        total_count = (await cursor.fetchone())[0]

        # Data query with rank via ROW_NUMBER
        # We need rank based on the unfiltered sort order for is_archive detection
        data_sql = f"""
            SELECT c.*,
                   ROW_NUMBER() OVER (ORDER BY c.{sort_by} {sort_direction}) as rank
            FROM wallet_leaderboard_cache c
            {join_sql}
            {where_sql}
            ORDER BY c.{sort_by} {sort_direction}
            LIMIT ? OFFSET ?
        """
        params_page = params + [limit, offset]
        cursor = await conn.execute(data_sql, params_page)
        rows = [dict(r) for r in await cursor.fetchall()]

        # Get cache freshness
        cursor = await conn.execute("SELECT MAX(computed_at) FROM wallet_leaderboard_cache")
        computed_at_row = await cursor.fetchone()
        computed_at = computed_at_row[0] if computed_at_row else None

    # Build response
    leaderboard = []
    for row in rows:
        rank = row.get("rank", 0)
        leaderboard.append({
            "wallet_address": row["wallet_address"],
            "rank": rank,
            "is_archive": is_search and rank > 100,
            "total_pnl_usd": row["total_pnl_usd"],
            "realized_pnl_usd": row["realized_pnl_usd"],
            "unrealized_pnl_usd": row["unrealized_pnl_usd"],
            "pnl_1d_usd": row["pnl_1d_usd"],
            "pnl_7d_usd": row["pnl_7d_usd"],
            "pnl_30d_usd": row["pnl_30d_usd"],
            "tokens_traded": row["tokens_traded"],
            "tokens_won": row["tokens_won"],
            "tokens_lost": row["tokens_lost"],
            "win_rate": row["win_rate"],
            "best_trade_pnl": row["best_trade_pnl"],
            "best_trade_token": row["best_trade_token"],
            "worst_trade_pnl": row["worst_trade_pnl"],
            "worst_trade_token": row["worst_trade_token"],
            "tags": json.loads(row["tags_json"]) if row["tags_json"] else [],
            "wallet_balance_usd": row["wallet_balance_usd"],
            "avg_entry_seconds": row["avg_entry_seconds"],
            "wallet_created_at": row["wallet_created_at"],
            "avg_hold_hours_7d": row["avg_hold_hours_7d"],
            "tiers": json.loads(row["tiers_json"]) if row["tiers_json"] else {},
            "tier_score": row["tier_score"],
            "home_runs": row["home_runs"],
            "rugs": row["rugs"],
        })

    return {
        "wallets": leaderboard,
        "total": total_count,
        "limit": limit, "offset": offset, "sort_by": sort_by, "sort_dir": sort_dir,
        "is_search": is_search,
        "computed_at": computed_at,
    }


@router.post("/api/leaderboard/rebuild")
async def rebuild_leaderboard(request: Request):
    """Manually trigger leaderboard cache rebuild."""
    from meridinate.services.leaderboard_cache import rebuild_leaderboard_cache
    result = await asyncio.get_event_loop().run_in_executor(None, rebuild_leaderboard_cache)
    return result


@router.get("/api/wallets/{wallet_address}/profile")
async def get_wallet_profile(request: Request, wallet_address: str):
    """Get detailed profile for a single wallet. Computed on-the-fly from position data."""
    from datetime import datetime as dt, timezone

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        # Get per-token data from mtew_token_positions + analyzed_tokens
        cursor = await conn.execute("""
            SELECT mtp.token_id, mtp.wallet_address,
                   COALESCE(mtp.total_bought_usd, 0) as total_bought_usd,
                   COALESCE(mtp.total_sold_usd, 0) as total_sold_usd,
                   COALESCE(mtp.realized_pnl, 0) as realized_pnl_usd,
                   mtp.still_holding, mtp.current_balance, mtp.current_balance_usd,
                   (COALESCE(mtp.buy_count, 1) + COALESCE(mtp.sell_count, 0)) as trade_count,
                   mtp.position_checked_at as last_trade_timestamp,
                   at.token_name, at.token_symbol, at.token_address, at.dex_id,
                   at.market_cap_usd as analysis_mc,
                   at.market_cap_usd_current as current_mc,
                   at.market_cap_ath as ath_mc,
                   at.analysis_timestamp as first_buy_timestamp,
                   (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = mtp.token_id
                    AND tt.tag IN ('verified-win', 'verified-loss') LIMIT 1) as verdict,
                   COALESCE(mtp.pnl_source, 'estimated') as _source
            FROM mtew_token_positions mtp
            JOIN analyzed_tokens at ON at.id = mtp.token_id
            WHERE mtp.wallet_address = ?
            ORDER BY COALESCE(mtp.realized_pnl, 0) DESC
        """, (wallet_address,))
        rows = [dict(r) for r in await cursor.fetchall()]

        # Collect token_ids already covered by mtew_token_positions
        position_token_ids = {r["token_id"] for r in rows}

        # Always check early_buyer_wallets for tokens NOT in mtew_token_positions
        # This handles both the full-fallback case (no positions at all) and
        # the hybrid case (some tokens have positions, others only have early_buyer data)
        cursor = await conn.execute("""
            SELECT ebw.token_id, ebw.wallet_address,
                   COALESCE(ebw.total_usd, 0) as total_bought_usd,
                   0 as total_sold_usd, 0 as realized_pnl_usd,
                   1 as still_holding, 0 as current_balance, 0 as current_balance_usd,
                   ebw.transaction_count as trade_count,
                   NULL as last_trade_timestamp,
                   at.token_name, at.token_symbol, at.token_address, at.dex_id,
                   at.market_cap_usd as analysis_mc,
                   at.market_cap_usd_current as current_mc,
                   at.market_cap_ath as ath_mc,
                   ebw.first_buy_timestamp,
                   (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = ebw.token_id
                    AND tt.tag IN ('verified-win', 'verified-loss') LIMIT 1) as verdict,
                   'estimated' as _source
            FROM early_buyer_wallets ebw
            JOIN analyzed_tokens at ON at.id = ebw.token_id AND (at.deleted_at IS NULL OR at.deleted_at = '')
            WHERE ebw.wallet_address = ?
        """, (wallet_address,))
        ebw_rows = [dict(r) for r in await cursor.fetchall()]

        # Merge: only add early_buyer rows for tokens not already in position data
        for r in ebw_rows:
            if r["token_id"] not in position_token_ids:
                rows.append(r)

        if not rows:
            raise HTTPException(status_code=404, detail=f"No data found for wallet {wallet_address}")

        # Get tags
        cursor = await conn.execute("SELECT tag FROM wallet_tags WHERE wallet_address = ?", (wallet_address,))
        tags = [r[0] for r in await cursor.fetchall()]

    # Aggregate profile from trades
    total_pnl = 0
    realized = 0
    unrealized = 0
    wins = 0
    losses = 0
    best_pnl = 0
    best_token = None
    worst_pnl = 0
    worst_token = None

    trades = []
    for r in rows:
        bought = r.get("total_bought_usd") or 0
        sold = r.get("total_sold_usd") or 0
        verdict = r.get("verdict")
        source = r.get("_source", "position")

        if source == "helius_enhanced":
            # Real PnL from actual swap transactions
            real = r.get("realized_pnl_usd") or 0
            holding = r.get("still_holding", 1)
            cur_usd = r.get("current_balance_usd") or 0
            unreal = (cur_usd - bought) if holding else 0
            t_pnl = real + unreal
        else:
            # No real PnL data — show 0
            t_pnl = 0
            real = 0
            unreal = 0
            cur_usd = 0

        total_pnl += t_pnl
        realized += real
        unrealized += unreal

        if verdict == "verified-win":
            wins += 1
        elif verdict == "verified-loss":
            losses += 1

        if t_pnl > best_pnl:
            best_pnl = t_pnl
            best_token = r.get("token_name")
        if t_pnl < worst_pnl:
            worst_pnl = t_pnl
            worst_token = r.get("token_name")

        trades.append({
            "token_id": r.get("token_id"),
            "token_address": r.get("token_address"),
            "token_name": r.get("token_name"),
            "token_symbol": r.get("token_symbol"),
            "dex_id": r.get("dex_id"),
            "analysis_mc": r.get("analysis_mc"),
            "total_bought_usd": bought,
            "total_sold_usd": sold,
            "realized_pnl_usd": round(real, 2),
            "unrealized_pnl_usd": round(unreal, 2),
            "total_pnl_usd": round(t_pnl, 2),
            "current_holdings": r.get("current_balance") or 0,
            "current_holdings_usd": round(cur_usd, 2),
            "trade_count": r.get("trade_count") or 1,
            "first_buy_timestamp": r.get("first_buy_timestamp"),
            "last_trade_timestamp": r.get("last_trade_timestamp"),
            "pnl_source": source,
        })

    tt = len(rows)
    return {
        "wallet_address": wallet_address,
        "total_pnl_usd": round(total_pnl, 2),
        "realized_pnl_usd": round(realized, 2),
        "unrealized_pnl_usd": round(unrealized, 2),
        "tokens_traded": tt,
        "tokens_won": wins,
        "tokens_lost": losses,
        "win_rate": round(wins / tt, 2) if tt > 0 else 0,
        "best_trade_pnl": round(best_pnl, 2),
        "best_trade_token": best_token,
        "worst_trade_pnl": round(worst_pnl, 2),
        "worst_trade_token": worst_token,
        "computed_at": dt.now(timezone.utc).isoformat(),
        "tags": tags,
        "trades": trades,
    }


    # compute-pnl endpoint removed — PnL is now computed from mtew_token_positions
    # by the Position Checker automatically. No manual trigger needed.


@router.get("/api/tokens/{token_id}/wallet-pnl")
async def get_token_wallet_pnl(token_id: int):
    """Get PnL data for all wallets in a specific token. Reads from mtew_token_positions."""
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT mtp.wallet_address,
                   mtp.total_bought_usd,
                   mtp.total_sold_usd,
                   COALESCE(mtp.realized_pnl, 0) as realized_pnl_usd,
                   CASE WHEN mtp.still_holding = 1
                        THEN COALESCE(mtp.current_balance_usd, 0) - COALESCE(mtp.total_bought_usd, 0)
                        ELSE 0 END as unrealized_pnl_usd,
                   CASE WHEN mtp.still_holding = 1
                        THEN COALESCE(mtp.current_balance_usd, 0) - COALESCE(mtp.total_bought_usd, 0) + COALESCE(mtp.realized_pnl, 0)
                        ELSE COALESCE(mtp.realized_pnl, 0) END as total_pnl_usd,
                   COALESCE(mtp.current_balance, 0) as current_holdings,
                   COALESCE(mtp.current_balance_usd, 0) as current_holdings_usd,
                   (COALESCE(mtp.buy_count, 1) + COALESCE(mtp.sell_count, 0)) as trade_count,
                   CASE WHEN mtp.still_holding = 1 THEN 'holding' ELSE 'exited' END as status,
                   COALESCE(mtp.pnl_source, 'estimated') as pnl_source,
                   mtp.entry_timestamp,
                   ebw.avg_entry_seconds
            FROM mtew_token_positions mtp
            LEFT JOIN early_buyer_wallets ebw ON ebw.wallet_address = mtp.wallet_address AND ebw.token_id = mtp.token_id
            WHERE mtp.token_id = ?
            """,
            (token_id,),
        )
        rows = [dict(r) for r in await cursor.fetchall()]
        # Sort: holding first, then by total_pnl descending
        rows.sort(key=lambda r: (0 if r["status"] == "holding" else 1, -(r["total_pnl_usd"] or 0)))
        pnl_map = {r["wallet_address"]: r for r in rows}
        return {"token_id": token_id, "pnl": pnl_map, "positions": rows}


@router.post("/api/tokens/{token_id}/compute-wallet-pnl")
async def compute_token_wallet_pnl(token_id: int):
    """Re-read PnL from position data. No Helius credits — just reads mtew_token_positions."""
    return await get_token_wallet_pnl(token_id)


@router.get("/api/token-leaderboard")
async def get_token_leaderboard(
    request: Request,
    sort_by: str = Query("score_composite", description="Sort field"),
    sort_dir: str = Query("desc", description="asc or desc"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: str = Query("", description="Search by token address, name, or symbol"),
    status: str = Query("", description="Filter: 'polled' for actively tracked tokens"),
    starred_only: bool = Query(False, description="Show only starred tokens"),
    w_momentum: float = Query(0.4, ge=0, le=1, description="Momentum weight"),
    w_smart: float = Query(0.35, ge=0, le=1, description="Smart Money weight"),
    w_risk: float = Query(0.25, ge=0, le=1, description="Risk weight"),
):
    """
    Token Leaderboard — full database search with scoring and pagination.
    Supports search by address/name/symbol and status filtering.
    """
    from meridinate.tasks.token_scorer import compute_composite_score

    allowed_sorts = {"score_composite", "score_momentum", "score_smart_money", "score_risk",
                     "market_cap_usd_current", "market_cap_ath", "analysis_timestamp",
                     "liquidity_usd", "credits_used"}
    if sort_by not in allowed_sorts:
        sort_by = "score_composite"
    direction = "DESC" if sort_dir.lower() == "desc" else "ASC"
    search_query = search.strip().lower()

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        # Build WHERE clause
        wheres = ["(deleted_at IS NULL OR deleted_at = '')"]
        params: list = []

        if search_query:
            wheres.append("(LOWER(token_address) LIKE ? OR LOWER(token_name) LIKE ? OR LOWER(token_symbol) LIKE ?)")
            sq = f"%{search_query}%"
            params.extend([sq, sq, sq])

        if status == "polled":
            wheres.append("market_cap_updated_at IS NOT NULL AND market_cap_updated_at >= datetime('now', '-24 hours')")

        if starred_only:
            wheres.append("token_address IN (SELECT item_address FROM starred_items WHERE item_type = 'token')")

        where_sql = " AND ".join(wheres)

        # Count
        cursor = await conn.execute(f"SELECT COUNT(*) FROM analyzed_tokens WHERE {where_sql}", params)
        total = (await cursor.fetchone())[0]

        # Sort: handle NULLs for unscored tokens
        null_handling = "NULLS LAST" if direction == "DESC" else "NULLS FIRST"

        cursor = await conn.execute(f"""
            SELECT id, token_address, token_name, token_symbol, dex_id, is_cashback,
                   market_cap_usd, market_cap_usd_current, market_cap_ath,
                   market_cap_usd_previous,
                   liquidity_usd, analysis_timestamp,
                   score_momentum, score_smart_money, score_risk, score_composite,
                   mint_authority_revoked, freeze_authority_active,
                   holder_top1_pct, holder_top10_pct, holder_count_latest,
                   score_updated_at,
                   credits_used, last_analysis_credits,
                   (SELECT COUNT(DISTINCT ebw.wallet_address) FROM early_buyer_wallets ebw WHERE ebw.token_id = analyzed_tokens.id) as wallets_found,
                   (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = analyzed_tokens.id AND tt.tag IN ('verified-win', 'verified-loss') LIMIT 1) as verdict,
                   (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = analyzed_tokens.id AND tt.tag LIKE 'win:%' LIMIT 1) as win_multiplier,
                   (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = analyzed_tokens.id AND tt.tag LIKE 'loss:%' LIMIT 1) as loss_tier,
                   holder_velocity, mc_volatility, mc_recovery_count, smart_money_flow, deployer_is_top_holder,
                   deployer_address, fresh_wallet_pct, fresh_at_deploy_count, fresh_at_deploy_total,
                   controlled_supply_score, fresh_supply_pct,
                   bundle_cluster_count, bundle_cluster_size,
                   stealth_holder_count, stealth_holder_pct,
                   has_meteora_pool, meteora_pool_address, meteora_pool_created_at, meteora_pool_creator,
                   meteora_creator_linked, meteora_link_type,
                   meteora_lp_activity_json,
                   market_cap_ath_timestamp,
                   clobr_score, rug_score, rug_label
            FROM analyzed_tokens
            WHERE {where_sql}
            ORDER BY {sort_by} {direction}
            LIMIT ? OFFSET ?
        """, params + [limit, offset])
        rows = [dict(r) for r in await cursor.fetchall()]

        # Compute deployer win rates for all tokens in one batch
        deployer_addresses = list(set(r["deployer_address"] for r in rows if r.get("deployer_address")))
        deployer_win_rates = {}
        if deployer_addresses:
            placeholders = ",".join("?" for _ in deployer_addresses)
            cursor = await conn.execute(f"""
                SELECT t.deployer_address,
                       COUNT(*) as cnt,
                       SUM(CASE WHEN (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = t.id AND tt.tag = 'verified-win' LIMIT 1) IS NOT NULL THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = t.id AND tt.tag = 'verified-loss' LIMIT 1) IS NOT NULL THEN 1 ELSE 0 END) as losses
                FROM analyzed_tokens t
                WHERE t.deployer_address IN ({placeholders}) AND (t.deleted_at IS NULL OR t.deleted_at = '')
                GROUP BY t.deployer_address
            """, deployer_addresses)
            for dr in await cursor.fetchall():
                total_v = (dr[2] or 0) + (dr[3] or 0)
                deployer_win_rates[dr[0]] = {
                    "tokens_deployed": dr[1],
                    "wins": dr[2] or 0,
                    "win_rate": round((dr[2] or 0) / total_v * 100) if total_v > 0 else None,
                }

        # Compute aggregate real PnL per token
        token_ids = [r["id"] for r in rows]
        token_pnl_agg = {}
        if token_ids:
            placeholders = ",".join("?" for _ in token_ids)
            cursor = await conn.execute(f"""
                SELECT token_id,
                       SUM(CASE WHEN pnl_source = 'helius_enhanced' THEN realized_pnl ELSE 0 END) as total_realized,
                       COUNT(CASE WHEN pnl_source = 'helius_enhanced' THEN 1 END) as real_count
                FROM mtew_token_positions
                WHERE token_id IN ({placeholders})
                GROUP BY token_id
            """, token_ids)
            for pr in await cursor.fetchall():
                token_pnl_agg[pr[0]] = {
                    "total_realized_pnl": round(pr[1] or 0, 2),
                    "real_pnl_count": pr[2] or 0,
                }

    # Enrich rows with deployer and PnL data
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    for row in rows:
        # Deployer win rate
        dep = row.get("deployer_address")
        dwr = deployer_win_rates.get(dep, {})
        row["deployer_win_rate"] = dwr.get("win_rate")
        row["deployer_tokens_deployed"] = dwr.get("tokens_deployed", 0)

        # Time since ATH
        ath_ts = row.get("market_cap_ath_timestamp")
        if ath_ts:
            try:
                ts = str(ath_ts)
                if "T" in ts:
                    ath_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                else:
                    ath_time = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                row["hours_since_ath"] = round((now - ath_time).total_seconds() / 3600, 1)
            except Exception:
                row["hours_since_ath"] = None
        else:
            row["hours_since_ath"] = None

        # Aggregate PnL
        pnl = token_pnl_agg.get(row["id"], {})
        row["aggregate_realized_pnl"] = pnl.get("total_realized_pnl", 0)
        row["real_pnl_wallets"] = pnl.get("real_pnl_count", 0)

        # MC direction (up/down/flat based on current vs previous)
        mc_cur = row.get("market_cap_usd_current") or 0
        mc_prev = row.get("market_cap_usd_previous") or mc_cur
        if mc_prev > 0 and mc_cur > 0:
            change_pct = ((mc_cur - mc_prev) / mc_prev) * 100
            row["mc_direction"] = "up" if change_pct > 1 else "down" if change_pct < -1 else "flat"
            row["mc_change_pct"] = round(change_pct, 1)
        else:
            row["mc_direction"] = "flat"
            row["mc_change_pct"] = 0

    # Recompute composite with custom weights if different from default
    if abs(w_momentum - 0.4) > 0.01 or abs(w_smart - 0.35) > 0.01 or abs(w_risk - 0.25) > 0.01:
        for row in rows:
            m = row.get("score_momentum") or 0
            s = row.get("score_smart_money") or 0
            r = row.get("score_risk") or 0
            row["score_composite"] = compute_composite_score(m, s, r, w_momentum, w_smart, w_risk)
        # Re-sort by composite if that's the sort field
        if sort_by == "score_composite":
            rows.sort(key=lambda x: x.get("score_composite") or 0, reverse=(direction == "DESC"))

    return {
        "tokens": rows,
        "total": total,
        "limit": limit, "offset": offset,
        "sort_by": sort_by, "sort_dir": sort_dir,
        "is_search": bool(search_query),
        "weights": {"momentum": w_momentum, "smart_money": w_smart, "risk": w_risk},
    }
