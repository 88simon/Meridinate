"""
Wallets router - multi-token wallets and balance refresh endpoints

Provides REST endpoints for wallet operations
"""

import asyncio
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Body, HTTPException, Request

from meridinate.middleware.rate_limit import READ_RATE_LIMIT, WALLET_BALANCE_RATE_LIMIT, conditional_rate_limit

from meridinate import settings
from meridinate import analyzed_tokens_db as db
from meridinate.cache import ResponseCache
from meridinate.credit_tracker import credit_tracker, CreditOperation
from meridinate.utils.models import MultiTokenWalletsResponse, RefreshBalancesRequest, RefreshBalancesResponse
import json

router = APIRouter()
cache = ResponseCache()

# Freshness tiers: (max_hours, tag_label)
# Order matters — tightest tier first, only one tag assigned per wallet
FRESHNESS_TIERS = [
    (1, "Fresh at Entry (<1h)"),
    (24, "Fresh at Entry (<24h)"),
    (72, "Fresh at Entry (<3d)"),
    (168, "Fresh at Entry (<7d)"),
]

# All possible freshness tags for cleanup
FRESHNESS_TAGS = [label for _, label in FRESHNESS_TIERS]


def _compute_freshness_tags(enrichment_results: list):
    """
    Compute freshness tags for wallets based on wallet creation date vs
    earliest token appearance. Uses funded-by date from enrichment data
    and earliest analysis_timestamp from early_buyer_wallets.
    """
    # Collect wallet addresses that have funded-by dates
    wallet_dates = {}
    for r in enrichment_results:
        addr = r.get("wallet_address")
        funded_by = r.get("funded_by")
        if addr and funded_by and funded_by.get("date"):
            try:
                date_str = funded_by["date"]
                # Parse ISO date from Helius (e.g., "2022-04-07T18:30:15.000Z")
                wallet_created = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                wallet_dates[addr] = wallet_created
            except (ValueError, TypeError):
                pass

    if not wallet_dates:
        return

    # Query earliest token appearance for these wallets
    addresses = list(wallet_dates.keys())
    with db.get_db_connection() as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" for _ in addresses)
        cursor.execute(f"""
            SELECT ebw.wallet_address, MIN(t.analysis_timestamp) as earliest_token
            FROM early_buyer_wallets ebw
            JOIN analyzed_tokens t ON ebw.token_id = t.id
            WHERE ebw.wallet_address IN ({placeholders})
            AND t.deleted_at IS NULL
            GROUP BY ebw.wallet_address
        """, addresses)
        rows = cursor.fetchall()

    # Compute freshness and assign tags
    tagged = 0
    for row in rows:
        addr, earliest_str = row[0], row[1]
        if addr not in wallet_dates or not earliest_str:
            continue

        try:
            # Parse analysis_timestamp
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
                try:
                    earliest_token = datetime.strptime(earliest_str, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            else:
                continue

            wallet_created = wallet_dates[addr]
            delta_hours = (earliest_token - wallet_created).total_seconds() / 3600

            # Only tag if wallet was created BEFORE the token (positive delta)
            # or very shortly after (within the tier window)
            if delta_hours < 0:
                delta_hours = abs(delta_hours)  # Created after token — still suspicious if very close

            # Remove any existing freshness tags first
            for old_tag in FRESHNESS_TAGS:
                try:
                    db.remove_wallet_tag(addr, old_tag)
                except Exception:
                    pass

            # Assign tightest matching tier
            for max_hours, tag_label in FRESHNESS_TIERS:
                if delta_hours <= max_hours:
                    try:
                        db.add_wallet_tag(addr, tag_label, tier=1, source="helius:funded-by")
                        tagged += 1
                    except Exception:
                        pass
                    break
        except Exception:
            continue

    if tagged > 0:
        from meridinate.observability import log_info
        log_info(f"[Enrichment] Tagged {tagged} wallets with freshness labels")


@router.get("/multi-token-wallets", response_model=MultiTokenWalletsResponse)
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_multi_early_buyer_wallets(request: Request, min_tokens: int = 2):
    """Get wallets that appear in multiple tokens"""
    cache_key = f"multi_early_buyer_wallets_{min_tokens}"
    cached_data, _ = cache.get(cache_key)
    if cached_data:
        return cached_data

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        query = """
            WITH distinct_wallet_tokens AS (
                SELECT DISTINCT
                    tw.wallet_address,
                    tw.token_id,
                    t.id as token_table_id,
                    t.token_name,
                    t.token_address,
                    tw.wallet_balance_usd,
                    tw.wallet_balance_usd_previous,
                    tw.wallet_balance_updated_at
                FROM early_buyer_wallets tw
                JOIN analyzed_tokens t ON tw.token_id = t.id
                WHERE t.deleted_at IS NULL
                ORDER BY t.id DESC
            )
            SELECT
                dwt.wallet_address,
                COUNT(DISTINCT dwt.token_id) as token_count,
                GROUP_CONCAT(dwt.token_name) as token_names,
                GROUP_CONCAT(dwt.token_address) as token_addresses,
                GROUP_CONCAT(dwt.token_table_id) as token_ids,
                MAX(dwt.wallet_balance_usd) as wallet_balance_usd,
                MAX(dwt.wallet_balance_usd_previous) as wallet_balance_usd_previous,
                MAX(dwt.wallet_balance_updated_at) as wallet_balance_updated_at,
                COALESCE(mtw.marked_new, 0) as is_new,
                mtw.marked_at_analysis_id
            FROM distinct_wallet_tokens dwt
            LEFT JOIN multi_token_wallet_metadata mtw ON dwt.wallet_address = mtw.wallet_address
            GROUP BY dwt.wallet_address
            HAVING COUNT(DISTINCT dwt.token_id) >= ?
            ORDER BY token_count DESC, wallet_balance_usd DESC
        """
        cursor = await conn.execute(query, (min_tokens,))
        rows = await cursor.fetchall()

        # Fetch all token tags for tokens that appear in the results
        all_token_ids = set()
        for row in rows:
            wallet_dict = dict(row)
            token_ids_str = wallet_dict.get("token_ids", "")
            if token_ids_str:
                all_token_ids.update([int(id) for id in token_ids_str.split(",")])

        # Fetch tags for all tokens at once
        tags_by_token = {}
        if all_token_ids:
            tags_query = "SELECT token_id, tag FROM token_tags WHERE token_id IN ({})".format(
                ",".join(str(tid) for tid in all_token_ids)
            )
            tag_cursor = await conn.execute(tags_query)
            tag_rows = await tag_cursor.fetchall()
            for tag_row in tag_rows:
                token_id, tag = tag_row[0], tag_row[1]
                if token_id not in tags_by_token:
                    tags_by_token[token_id] = []
                tags_by_token[token_id].append(tag)

        wallets = []
        for row in rows:
            wallet_dict = dict(row)
            wallet_dict["token_names"] = wallet_dict["token_names"].split(",") if wallet_dict["token_names"] else []
            wallet_dict["token_addresses"] = (
                wallet_dict["token_addresses"].split(",") if wallet_dict["token_addresses"] else []
            )
            token_ids = [int(id) for id in wallet_dict["token_ids"].split(",") if wallet_dict["token_ids"]]
            wallet_dict["token_ids"] = token_ids

            # Build verdicts and win multipliers from token tags
            verdicts = []
            win_multipliers = []
            for token_id in token_ids:
                tags = tags_by_token.get(token_id, [])
                if "verified-win" in tags:
                    verdicts.append("verified-win")
                elif "verified-loss" in tags:
                    verdicts.append("verified-loss")
                else:
                    verdicts.append(None)
                # Find win:* multiplier tag if present
                mult = next((t for t in tags if t.startswith("win:")), None)
                win_multipliers.append(mult)
            wallet_dict["verdicts"] = verdicts
            wallet_dict["win_multipliers"] = win_multipliers

            # Convert is_new from integer (0/1) to boolean
            wallet_dict["is_new"] = bool(wallet_dict["is_new"])
            # SQLite returns timestamps as strings; pass through for client consumption
            wallets.append(wallet_dict)

        result = {"total": len(wallets), "wallets": wallets}
        cache.set(cache_key, result)
        return result


@router.post("/wallets/refresh-balances", response_model=RefreshBalancesResponse)
@conditional_rate_limit(WALLET_BALANCE_RATE_LIMIT)
async def refresh_wallet_balances(request: Request, data: RefreshBalancesRequest):
    """Refresh wallet balances for multiple wallets using the Wallet API.

    Uses the Helius Wallet API /v1/wallet/{addr}/balances endpoint which returns
    all token holdings with USD values in a single call (100 credits per wallet).
    """
    wallet_addresses = data.wallet_addresses

    from meridinate.helius_api import HeliusAPI

    helius = HeliusAPI(settings.HELIUS_API_KEY)

    # Capture existing balances for comparison
    existing_balances = {}
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        placeholders = ",".join("?" for _ in wallet_addresses)
        if placeholders:
            cursor = await conn.execute(
                f"SELECT wallet_address, wallet_balance_usd FROM early_buyer_wallets WHERE wallet_address IN ({placeholders})",
                wallet_addresses,
            )
            for row in await cursor.fetchall():
                existing_balances[row[0]] = row[1]

    async def fetch_balance(wallet_address: str):
        try:
            loop = asyncio.get_event_loop()
            balances_data, credits = await loop.run_in_executor(
                None, lambda: helius.get_wallet_balances(wallet_address)
            )

            if balances_data is not None:
                total_usd = balances_data.get("totalUsdValue", 0.0)
                return {
                    "wallet_address": wallet_address,
                    "balance_usd": total_usd,
                    "success": True,
                    "credits": credits,
                }
            else:
                return {"wallet_address": wallet_address, "balance_usd": None, "success": False, "credits": credits}
        except Exception:
            return {"wallet_address": wallet_address, "balance_usd": None, "success": False, "credits": 0}

    # Fetch all balances concurrently
    results = await asyncio.gather(*[fetch_balance(addr) for addr in wallet_addresses])

    # Update database with previous/current values and timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        for result in results:
            if result["success"] and result["balance_usd"] is not None:
                await conn.execute(
                    """
                    UPDATE early_buyer_wallets
                    SET wallet_balance_usd_previous = wallet_balance_usd,
                        wallet_balance_usd = ?,
                        wallet_balance_updated_at = ?
                    WHERE wallet_address = ?
                    """,
                    (result["balance_usd"], timestamp, result["wallet_address"]),
                )
                result["previous_balance_usd"] = existing_balances.get(result["wallet_address"])
                result["updated_at"] = timestamp
            else:
                result["previous_balance_usd"] = existing_balances.get(result["wallet_address"])
                result["updated_at"] = None
        await conn.commit()

    cache.invalidate("multi_early_buyer_wallets")

    successful = sum(1 for r in results if r["success"])
    total_credits = sum(r.get("credits", 0) for r in results)

    # Record batch wallet refresh credits
    if total_credits > 0:
        credit_tracker.record_batch(
            CreditOperation.WALLET_REFRESH,
            credits=total_credits,
            count=len(wallet_addresses),
            context={"successful": successful},
        )
        # Log to operation log for the credits panel
        from meridinate.credit_tracker import get_credit_tracker
        get_credit_tracker().record_operation(
            operation="wallet_refresh",
            label="Wallet Balance Refresh",
            credits=total_credits,
            call_count=len(wallet_addresses),
            context={"successful": successful},
        )

    return {
        "message": f"Refreshed {successful} of {len(wallet_addresses)} wallets",
        "results": results,
        "total_wallets": len(wallet_addresses),
        "successful": successful,
        "api_credits_used": total_credits,
    }


@router.get("/wallets/{wallet_address}/top-holder-tokens")
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_wallet_top_holder_tokens(request: Request, wallet_address: str):
    """
    Get all tokens where this wallet is a top holder.

    Returns a list of tokens with:
    - token_id
    - token_name
    - token_symbol
    - token_address
    - top_holders (full list from top_holders_json)
    - top_holders_limit (the limit used when analyzing)
    - wallet_rank (this wallet's position in the top holders list, 1-indexed)
    - last_updated (when top holders was last refreshed)
    """
    cache_key = f"wallet_top_holder_tokens_{wallet_address}"
    cached_data, _ = cache.get(cache_key)
    if cached_data:
        return cached_data

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        # Get all tokens where top_holders_json is not NULL and deleted_at is NULL
        query = """
            SELECT
                id,
                token_name,
                token_symbol,
                token_address,
                top_holders_json,
                top_holders_updated_at
            FROM analyzed_tokens
            WHERE top_holders_json IS NOT NULL
              AND deleted_at IS NULL
        """
        cursor = await conn.execute(query)
        rows = await cursor.fetchall()

        top_holder_tokens = []

        for row in rows:
            row_dict = dict(row)
            top_holders_json = row_dict.get("top_holders_json")

            if not top_holders_json:
                continue

            try:
                holders = json.loads(top_holders_json)

                # Check if wallet_address is in the top holders list
                wallet_rank = None
                for idx, holder in enumerate(holders):
                    if holder.get("address") == wallet_address:
                        wallet_rank = idx + 1  # 1-indexed
                        break

                if wallet_rank is not None:
                    # This wallet is a top holder of this token
                    top_holder_tokens.append({
                        "token_id": row_dict["id"],
                        "token_name": row_dict["token_name"],
                        "token_symbol": row_dict["token_symbol"],
                        "token_address": row_dict["token_address"],
                        "top_holders": holders,
                        "top_holders_limit": len(holders),  # The actual number of holders stored
                        "wallet_rank": wallet_rank,
                        "last_updated": row_dict["top_holders_updated_at"]
                    })
            except (json.JSONDecodeError, KeyError, TypeError):
                # Skip tokens with malformed data
                continue

        result = {
            "wallet_address": wallet_address,
            "total_tokens": len(top_holder_tokens),
            "tokens": top_holder_tokens
        }

        # Cache with default TTL (30s) - must match batch-top-holder-counts TTL
        # to prevent badge/modal desync when top_holders_json is updated
        cache.set(cache_key, result)
        return result


@router.post("/wallets/batch-top-holder-counts")
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_batch_top_holder_counts(request: Request, wallet_addresses: list[str] = Body(embed=True)):
    """
    Get count of tokens where each wallet is a top holder.
    Optimized batch endpoint that returns only counts, not full holder lists.

    This is much more efficient than calling /wallets/{address}/top-holder-tokens
    for each wallet when you only need the counts for badge display.

    Request body: {"wallet_addresses": ["addr1", "addr2", ...]}
    Returns: {"counts": {"addr1": 3, "addr2": 5, ...}}
    """
    cache_key = f"batch_top_holder_counts_{hash(tuple(sorted(wallet_addresses)))}"
    cached_data, _ = cache.get(cache_key)
    if cached_data:
        return cached_data

    counts = {}

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        # Get all tokens where top_holders_json is not NULL
        query = """
            SELECT top_holders_json
            FROM analyzed_tokens
            WHERE top_holders_json IS NOT NULL
              AND deleted_at IS NULL
        """
        cursor = await conn.execute(query)
        rows = await cursor.fetchall()

        # Build a count map for each wallet address
        for wallet_address in wallet_addresses:
            count = 0
            for row in rows:
                top_holders_json = row[0]
                if not top_holders_json:
                    continue

                try:
                    holders = json.loads(top_holders_json)
                    # Check if wallet_address is in this token's holders
                    if any(holder.get("address") == wallet_address for holder in holders):
                        count += 1
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue

            counts[wallet_address] = count

    result = {"counts": counts}

    # Cache result (ResponseCache uses default 30s TTL)
    cache.set(cache_key, result)
    return result


# ============================================================================
# Wallet API Endpoints (Helius Wallet API v1 integrations)
# ============================================================================


@router.get("/wallets/cached-intel")
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_cached_wallet_intel(request: Request):
    """
    Get cached enrichment intel for all wallets. Reads from wallet_enrichment_cache
    and wallet_tags — no API calls, instant response. Used to populate the Intel
    column on the Wallet Intel page without re-running Enrich Wallets.
    """
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        # Get funded-by data from enrichment cache
        cursor = await conn.execute("""
            SELECT wallet_address, funded_by_json, identity_json
            FROM wallet_enrichment_cache
            WHERE funded_by_json IS NOT NULL OR identity_json IS NOT NULL
        """)
        cache_rows = await cursor.fetchall()

        funded_by_map = {}
        identities_map = {}

        for row in cache_rows:
            addr = row["wallet_address"]
            if row["funded_by_json"]:
                try:
                    fb = json.loads(row["funded_by_json"])
                    if fb and fb.get("funder"):
                        funded_by_map[addr] = {
                            "funder": fb["funder"],
                            "funderName": fb.get("funderName"),
                            "funderType": fb.get("funderType"),
                        }
                except Exception:
                    pass
            if row["identity_json"]:
                try:
                    ident = json.loads(row["identity_json"])
                    if ident and ident.get("name"):
                        identities_map[addr] = {
                            "name": ident["name"],
                            "type": ident.get("type"),
                            "category": ident.get("category"),
                            "tags": ident.get("tags", []),
                        }
                except Exception:
                    pass

        # Build clusters from funded-by data
        funder_groups = {}
        for addr, fb in funded_by_map.items():
            funder = fb["funder"]
            if funder not in funder_groups:
                funder_groups[funder] = {
                    "funder": funder,
                    "funder_name": fb.get("funderName"),
                    "funder_type": fb.get("funderType"),
                    "wallets": [],
                }
            funder_groups[funder]["wallets"].append(addr)

        clusters = sorted(
            [c for c in funder_groups.values() if len(c["wallets"]) > 1],
            key=lambda c: len(c["wallets"]), reverse=True
        )

    return {
        "fundedBy": funded_by_map,
        "identities": identities_map,
        "clusters": clusters,
        "total_cached": len(cache_rows),
    }


@router.get("/wallets/{wallet_address}/funded-by")
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_wallet_funded_by(request: Request, wallet_address: str):
    """
    Get the original funding source of a wallet.

    Returns the address that sent the first SOL transfer to this wallet.
    Useful for detecting wallet clusters — if multiple early bidders
    were all funded by the same source, that's a sybil/bot signal.

    Costs ~100 Helius credits per call.
    """
    cache_key = f"wallet_funded_by_{wallet_address}"
    cached_data, _ = cache.get(cache_key)
    if cached_data:
        return cached_data

    from meridinate.helius_api import HeliusAPI
    helius = HeliusAPI(settings.HELIUS_API_KEY)

    funded_by, credits = await asyncio.get_event_loop().run_in_executor(
        None, lambda: helius.get_wallet_funded_by(wallet_address)
    )

    result = {
        "wallet_address": wallet_address,
        "funded_by": funded_by,
        "credits_used": credits,
    }
    cache.set(cache_key, result)
    return result


@router.post("/wallets/batch-funded-by")
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_batch_funded_by(request: Request, wallet_addresses: list[str] = Body(embed=True)):
    """
    Batch lookup of funding sources for multiple wallets.

    Returns the funder for each wallet. Useful for grouping wallets
    by their original funding source to detect clusters.

    Costs ~100 Helius credits per wallet.
    """
    from meridinate.helius_api import HeliusAPI
    helius = HeliusAPI(settings.HELIUS_API_KEY)

    async def fetch_funded_by(addr: str):
        try:
            result, credits = await asyncio.get_event_loop().run_in_executor(
                None, lambda: helius.get_wallet_funded_by(addr)
            )
            return {
                "wallet_address": addr,
                "funded_by": result,
                "credits": credits,
            }
        except Exception:
            return {"wallet_address": addr, "funded_by": None, "credits": 0}

    results = await asyncio.gather(*[fetch_funded_by(addr) for addr in wallet_addresses])
    total_credits = sum(r.get("credits", 0) for r in results)

    # Build a funder_map: group wallets by their funder address
    funder_map = {}
    for r in results:
        funded_by = r.get("funded_by")
        if funded_by and funded_by.get("funder"):
            funder_addr = funded_by["funder"]
            if funder_addr not in funder_map:
                funder_map[funder_addr] = {
                    "funder": funder_addr,
                    "funder_name": funded_by.get("funderName"),
                    "funder_type": funded_by.get("funderType"),
                    "wallets": [],
                }
            funder_map[funder_addr]["wallets"].append(r["wallet_address"])

    # Sort clusters by number of wallets (largest first)
    clusters = sorted(funder_map.values(), key=lambda c: len(c["wallets"]), reverse=True)

    # --- Phase 2: Store enrichment data and compute Tier 1 tags ---
    for r in results:
        addr = r.get("wallet_address")
        funded_by = r.get("funded_by")
        if addr and funded_by:
            try:
                db.upsert_wallet_enrichment(addr, funded_by_json=json.dumps(funded_by))
            except Exception:
                pass  # best-effort persistence

    # Tag wallets that share a funder (cluster detection)
    for cluster in clusters:
        if len(cluster["wallets"]) >= 2:
            for addr in cluster["wallets"]:
                try:
                    db.add_wallet_tag(addr, "Cluster", tier=1, source="helius:funded-by")
                except Exception:
                    pass

    # Tag fresh wallets based on wallet age vs first token appearance
    await asyncio.to_thread(_compute_freshness_tags, results)

    # Log to operation log
    if total_credits > 0:
        from meridinate.credit_tracker import get_credit_tracker
        get_credit_tracker().record_operation(
            operation="wallet_enrichment",
            label="Wallet Enrichment (Funded-By)",
            credits=total_credits,
            call_count=len(wallet_addresses),
            context={"clusters_found": len([c for c in clusters if len(c["wallets"]) > 1])},
        )

    return {
        "results": results,
        "clusters": clusters,
        "total_credits": total_credits,
    }


@router.post("/wallets/trace-funding")
@conditional_rate_limit(READ_RATE_LIMIT)
async def trace_wallet_funding(
    request: Request,
    wallet_addresses: list[str] = Body(embed=True),
    max_hops: int = Body(default=3, ge=1, le=5),
    stop_at_exchanges: bool = Body(default=True),
):
    """
    Multi-hop funding trace for multiple wallets.
    Traces each wallet's funding chain through configurable depth (1-5 hops).
    Reveals hidden clusters where wallets converge at deeper hops.
    Uses caching so shared intermediary wallets are only traced once.

    Costs ~100 Helius credits per hop per wallet (minus cache hits).
    """
    from meridinate.services.funding_tracer import trace_batch_funding_chains

    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: trace_batch_funding_chains(
            wallet_addresses, settings.HELIUS_API_KEY, max_hops, stop_at_exchanges
        )
    )

    # Log operation
    if result.get("total_credits", 0) > 0:
        from meridinate.credit_tracker import get_credit_tracker
        get_credit_tracker().record_operation(
            operation="funding_trace",
            label="Multi-Hop Funding Trace",
            credits=result["total_credits"],
            call_count=len(wallet_addresses),
            context={"max_hops": max_hops, "deep_clusters": len(result.get("deep_clusters", []))},
        )

    return result


@router.post("/wallets/trace-forward")
@conditional_rate_limit(READ_RATE_LIMIT)
async def trace_wallet_forward(
    request: Request,
    wallet_address: str = Body(embed=True),
    max_hops: int = Body(default=2, ge=1, le=3),
    max_recipients: int = Body(default=10, ge=1, le=20),
):
    """
    Forward funding trace — where did this wallet SEND money?

    Reveals sybil distribution networks: a single funder creating
    multiple wallets that buy the same token.

    Costs ~100 credits per hop level (cached after first call).
    """
    from meridinate.services.funding_tracer import trace_forward_chain

    result = await asyncio.to_thread(
        trace_forward_chain,
        wallet_address, settings.HELIUS_API_KEY, max_hops, max_recipients
    )

    if result.get("credits_used", 0) > 0:
        from meridinate.credit_tracker import get_credit_tracker
        get_credit_tracker().record_operation(
            operation="forward_trace",
            label="Forward Funding Trace",
            credits=result["credits_used"],
            call_count=1,
            context={
                "wallet": wallet_address,
                "max_hops": max_hops,
                "recipients_found": result.get("total_recipients", 0),
                "cluster_tokens": len(result.get("cluster_tokens", [])),
            },
        )

    return result


@router.post("/wallets/batch-identity")
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_batch_wallet_identities(request: Request, wallet_addresses: list[str] = Body(embed=True)):
    """
    Batch lookup of wallet identities (up to 100 at once).

    Returns known identity info (exchange, protocol, name, category, tags)
    for each wallet address. Uses Helius's database of 5,100+ tagged accounts.

    Costs ~100 Helius credits per batch call.
    """
    from meridinate.helius_api import HeliusAPI
    helius = HeliusAPI(settings.HELIUS_API_KEY)

    identities, credits = await asyncio.get_event_loop().run_in_executor(
        None, lambda: helius.get_batch_wallet_identities(wallet_addresses)
    )

    # Build a lookup map for quick access
    identity_map = {}
    if identities:
        for identity in identities:
            addr = identity.get("address")
            if addr and identity.get("name"):
                identity_map[addr] = {
                    "name": identity.get("name"),
                    "type": identity.get("type"),
                    "category": identity.get("category"),
                    "tags": identity.get("tags", []),
                }

    # --- Phase 2: Store enrichment data and compute Tier 1 identity tags ---
    for addr, identity in identity_map.items():
        try:
            db.upsert_wallet_enrichment(addr, identity_json=json.dumps(identity))
        except Exception:
            pass  # best-effort persistence

        identity_type = (identity.get("type") or "").lower()
        identity_category = (identity.get("category") or "").lower()

        try:
            if identity_type == "exchange":
                db.add_wallet_tag(addr, "Exchange", tier=1, source="helius:identity")
            if identity_type == "protocol" or "defi" in identity_category:
                db.add_wallet_tag(addr, "Protocol", tier=1, source="helius:identity")
        except Exception:
            pass

    # Log to operation log
    if credits > 0:
        from meridinate.credit_tracker import get_credit_tracker
        get_credit_tracker().record_operation(
            operation="wallet_enrichment",
            label="Wallet Enrichment (Identity)",
            credits=credits,
            call_count=len(wallet_addresses),
            context={"identified": len(identity_map)},
        )

    return {
        "identities": identity_map,
        "total_identified": len(identity_map),
        "total_queried": len(wallet_addresses),
        "credits_used": credits,
    }


@router.post("/wallets/compute-tags")
@conditional_rate_limit(READ_RATE_LIMIT)
async def compute_wallet_tags(request: Request, wallet_addresses: list[str] = Body(embed=True)):
    """
    Compute Tier 2 tags for a batch of wallets.

    For each wallet, runs compute_wallet_tier2_tags() which derives tags like
    Consistent Winner, Consistent Loser, Diversified, and Sniper from
    Meridinate's own data (no external API calls).

    Returns the computed tags per wallet.
    """
    results = {}
    for addr in wallet_addresses:
        try:
            tags = db.compute_wallet_tier2_tags(addr)
            results[addr] = tags
        except Exception:
            results[addr] = []

    return {
        "tags": results,
        "total_wallets": len(wallet_addresses),
    }


@router.get("/wallets/{wallet_address}/transfers")
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_wallet_transfers(
    request: Request,
    wallet_address: str,
    limit: int = 50,
    cursor: str = None,
):
    """
    Get incoming/outgoing transfers for a wallet with counterparty info.

    Returns transfer events with direction (in/out), token, amount, counterparty,
    and timestamps. Useful for the Position Tracker to show actual transfer activity.

    Costs ~100 Helius credits per call.
    """
    cache_key = f"wallet_transfers_{wallet_address}_{limit}_{cursor}"
    cached_data, _ = cache.get(cache_key)
    if cached_data:
        return cached_data

    from meridinate.helius_api import HeliusAPI
    helius = HeliusAPI(settings.HELIUS_API_KEY)

    transfers, credits = await asyncio.get_event_loop().run_in_executor(
        None, lambda: helius.get_wallet_transfers(wallet_address, limit=limit, cursor=cursor)
    )

    result = {
        "wallet_address": wallet_address,
        "transfers": transfers.get("data", []) if transfers else [],
        "pagination": transfers.get("pagination", {}) if transfers else {},
        "credits_used": credits,
    }
    cache.set(cache_key, result)
    return result


@router.get("/wallets/intelligence/{wallet_address}")
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_wallet_intelligence(wallet_address: str, request: Request):
    """
    Comprehensive Wallet Intelligence Report.
    Stitches together: identity, funding, freshness, PnL, entry timing,
    token history, and behavioral patterns. Zero API calls — pure database.
    """
    import json as _json

    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        # === PROFILE ===
        # Wallet tags
        cursor = await conn.execute(
            "SELECT tag, tier, source FROM wallet_tags WHERE wallet_address = ?",
            (wallet_address,)
        )
        tags = [{"tag": r["tag"], "tier": r["tier"], "source": r["source"]} for r in await cursor.fetchall()]

        # Enrichment data (funded-by, identity)
        cursor = await conn.execute(
            "SELECT funded_by_json, identity_json FROM wallet_enrichment_cache WHERE wallet_address = ?",
            (wallet_address,)
        )
        enrichment = await cursor.fetchone()
        funded_by = None
        identity = None
        wallet_created_at = None
        if enrichment:
            if enrichment["funded_by_json"]:
                try:
                    funded_by = _json.loads(enrichment["funded_by_json"])
                    # Extract wallet creation date
                    fb_date = funded_by.get("date") or funded_by.get("timestamp")
                    if fb_date:
                        wallet_created_at = str(fb_date)
                except Exception:
                    pass
            if enrichment["identity_json"]:
                try:
                    identity = _json.loads(enrichment["identity_json"])
                except Exception:
                    pass

        # === EARLY BUYER PERFORMANCE ===
        cursor = await conn.execute("""
            SELECT ebw.token_id, ebw.first_buy_timestamp, ebw.total_usd,
                   ebw.wallet_balance_usd, ebw.avg_entry_seconds,
                   t.token_name, t.token_symbol, t.token_address,
                   t.first_buy_timestamp as token_creation_time,
                   t.market_cap_usd as analysis_mc,
                   t.market_cap_usd_current, t.market_cap_ath
            FROM early_buyer_wallets ebw
            JOIN analyzed_tokens t ON t.id = ebw.token_id
            WHERE ebw.wallet_address = ? AND (t.deleted_at IS NULL OR t.deleted_at = '')
            ORDER BY ebw.first_buy_timestamp ASC
        """, (wallet_address,))
        early_buys = [dict(r) for r in await cursor.fetchall()]

        # Compute entry timing deltas
        entry_deltas = []
        for buy in early_buys:
            if buy.get("first_buy_timestamp") and buy.get("token_creation_time"):
                try:
                    from datetime import datetime
                    buy_ts = buy["first_buy_timestamp"]
                    token_ts = buy["token_creation_time"]
                    bt = datetime.fromisoformat(str(buy_ts).replace("Z", "").split("+")[0])
                    tt = datetime.fromisoformat(str(token_ts).replace("Z", "").split("+")[0])
                    delta = (bt - tt).total_seconds()
                    if 0 <= delta < 86400:
                        entry_deltas.append(delta)
                        buy["entry_seconds"] = round(delta, 1)
                except Exception:
                    pass

        avg_entry_seconds = sum(entry_deltas) / len(entry_deltas) if entry_deltas else None
        pct_under_60s = (sum(1 for d in entry_deltas if d < 60) / len(entry_deltas) * 100) if entry_deltas else None

        # === REAL PNL ===
        cursor = await conn.execute("""
            SELECT mtp.token_id, mtp.total_bought_usd, mtp.total_sold_usd,
                   mtp.realized_pnl, mtp.still_holding, mtp.pnl_source,
                   t.token_name, t.token_symbol, t.token_address
            FROM mtew_token_positions mtp
            JOIN analyzed_tokens t ON t.id = mtp.token_id
            WHERE mtp.wallet_address = ? AND (t.deleted_at IS NULL OR t.deleted_at = '')
            ORDER BY mtp.realized_pnl DESC
        """, (wallet_address,))
        positions = [dict(r) for r in await cursor.fetchall()]

        # Compute PnL stats
        real_positions = [p for p in positions if p.get("pnl_source") == "helius_enhanced"]
        total_bought = sum(p.get("total_bought_usd") or 0 for p in real_positions)
        total_sold = sum(p.get("total_sold_usd") or 0 for p in real_positions)
        total_realized = sum(p.get("realized_pnl") or 0 for p in real_positions)
        wins = sum(1 for p in real_positions if (p.get("realized_pnl") or 0) > 0)
        losses = sum(1 for p in real_positions if (p.get("realized_pnl") or 0) < 0 and not p.get("still_holding"))
        total_with_outcome = wins + losses
        win_rate = round(wins / total_with_outcome * 100) if total_with_outcome > 0 else None
        still_holding = sum(1 for p in real_positions if p.get("still_holding"))

        best_trade = max(real_positions, key=lambda p: p.get("realized_pnl") or 0) if real_positions else None
        worst_trade = min(real_positions, key=lambda p: p.get("realized_pnl") or 0) if real_positions else None

        # === VERDICTS + TIERS on tokens this wallet bought ===
        token_ids = [b["token_id"] for b in early_buys]
        verdicts = {}
        win_multipliers = {}
        loss_tiers = {}
        if token_ids:
            placeholders = ",".join("?" for _ in token_ids)
            cursor = await conn.execute(
                f"SELECT token_id, tag FROM token_tags WHERE token_id IN ({placeholders}) AND (tag IN ('verified-win', 'verified-loss') OR tag LIKE 'win:%' OR tag LIKE 'loss:%')",
                token_ids
            )
            for r in await cursor.fetchall():
                tag = r["tag"]
                tid = r["token_id"]
                if tag in ('verified-win', 'verified-loss'):
                    verdicts[tid] = tag
                elif tag.startswith('win:'):
                    win_multipliers[tid] = tag
                elif tag.startswith('loss:'):
                    loss_tiers[tid] = tag

        # Enrich early buys with verdicts and PnL
        pnl_by_token = {p["token_id"]: p for p in positions}
        for buy in early_buys:
            tid = buy["token_id"]
            buy["verdict"] = verdicts.get(tid)
            buy["win_multiplier"] = win_multipliers.get(tid)
            buy["loss_tier"] = loss_tiers.get(tid)
            pnl = pnl_by_token.get(tid)
            if pnl and pnl.get("pnl_source") == "helius_enhanced":
                buy["realized_pnl"] = pnl.get("realized_pnl")
                buy["total_bought_usd"] = pnl.get("total_bought_usd")
                buy["total_sold_usd"] = pnl.get("total_sold_usd")
                buy["still_holding"] = pnl.get("still_holding")
                buy["pnl_source"] = "real"
            else:
                buy["realized_pnl"] = None
                buy["pnl_source"] = "none"

        # === DEPLOYER CHECK ===
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM analyzed_tokens WHERE deployer_address = ? AND (deleted_at IS NULL OR deleted_at = '')",
            (wallet_address,)
        )
        tokens_deployed = (await cursor.fetchone())[0]

        # === WALLET AGE relative to first buy ===
        first_buy_time = early_buys[0]["first_buy_timestamp"] if early_buys else None
        wallet_age_at_first_buy_hours = None
        if wallet_created_at and first_buy_time:
            try:
                from datetime import datetime
                wc = wallet_created_at
                if isinstance(wc, (int, float)):
                    wc_dt = datetime.utcfromtimestamp(wc)
                else:
                    wc_dt = datetime.fromisoformat(str(wc).replace("Z", "").split("+")[0])
                fb_dt = datetime.fromisoformat(str(first_buy_time).replace("Z", "").split("+")[0])
                wallet_age_at_first_buy_hours = round((fb_dt - wc_dt).total_seconds() / 3600, 1)
            except Exception:
                pass

    return {
        "wallet_address": wallet_address,

        "profile": {
            "tags": tags,
            "identity": identity,
            "funded_by": funded_by,
            "wallet_created_at": wallet_created_at,
            "wallet_age_at_first_buy_hours": wallet_age_at_first_buy_hours,
            "is_deployer": tokens_deployed > 0,
            "tokens_deployed": tokens_deployed,
        },

        "performance": {
            "tokens_bought_early": len(early_buys),
            "avg_entry_seconds": round(avg_entry_seconds, 1) if avg_entry_seconds is not None else None,
            "pct_entries_under_60s": round(pct_under_60s, 1) if pct_under_60s is not None else None,
            "total_bought_usd": round(total_bought, 2),
            "total_sold_usd": round(total_sold, 2),
            "total_realized_pnl": round(total_realized, 2),
            "win_rate": win_rate,
            "wins": wins,
            "losses": losses,
            "still_holding": still_holding,
            "real_pnl_count": len(real_positions),
            "best_trade": {
                "token_id": best_trade.get("token_id"),
                "token_name": best_trade.get("token_name"),
                "realized_pnl": round(best_trade.get("realized_pnl") or 0, 2),
            } if best_trade else None,
            "worst_trade": {
                "token_id": worst_trade.get("token_id"),
                "token_name": worst_trade.get("token_name"),
                "realized_pnl": round(worst_trade.get("realized_pnl") or 0, 2),
            } if worst_trade else None,
        },

        "trades": early_buys,
    }


@router.post("/wallets/pnl-backfill/start")
async def start_pnl_backfill(request: Request, min_tokens: int = 5):
    """Start PnL v2 backfill for wallets with min_tokens+ tokens."""
    from meridinate.services.pnl_backfill_manager import get_backfill_manager
    manager = get_backfill_manager()
    return await manager.start(min_token_count=min_tokens)


@router.post("/wallets/pnl-backfill/stop")
async def stop_pnl_backfill(request: Request):
    """Stop the running PnL backfill."""
    from meridinate.services.pnl_backfill_manager import get_backfill_manager
    return await get_backfill_manager().stop()


@router.get("/wallets/pnl-backfill/status")
async def get_pnl_backfill_status(request: Request):
    """Get PnL backfill progress."""
    from meridinate.services.pnl_backfill_manager import get_backfill_manager
    manager = get_backfill_manager()
    return {"running": manager.is_running, **manager.state}


@router.get("/wallets/deployer-profile/{deployer_address}")
@conditional_rate_limit(READ_RATE_LIMIT)
async def get_deployer_profile(deployer_address: str, request: Request):
    """
    Get all tokens deployed by a wallet, with their verdicts and performance.
    No API calls — reads directly from the database.
    """
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT t.id, t.token_address, t.token_name, t.token_symbol,
                   t.analysis_timestamp, t.market_cap_usd, t.market_cap_usd_current,
                   t.market_cap_ath, t.first_buy_timestamp, t.creation_events_json,
                   (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = t.id AND tt.tag IN ('verified-win', 'verified-loss') LIMIT 1) as verdict,
                   (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = t.id AND tt.tag LIKE 'win:%' LIMIT 1) as win_multiplier
            FROM analyzed_tokens t
            WHERE t.deployer_address = ? AND (t.deleted_at IS NULL OR t.deleted_at = '')
            ORDER BY t.analysis_timestamp DESC
        """, (deployer_address,))
        tokens = [dict(r) for r in await cursor.fetchall()]

    wins = sum(1 for t in tokens if t["verdict"] == "verified-win")
    losses = sum(1 for t in tokens if t["verdict"] == "verified-loss")
    total_with_verdict = wins + losses

    # Compute avg ATH multiple for winning tokens
    ath_multiples = []
    for t in tokens:
        if t["verdict"] == "verified-win" and t["market_cap_usd"] and t["market_cap_ath"]:
            if t["market_cap_usd"] > 0:
                ath_multiples.append(t["market_cap_ath"] / t["market_cap_usd"])

    return {
        "deployer_address": deployer_address,
        "tokens_deployed": len(tokens),
        "wins": wins,
        "losses": losses,
        "pending": len(tokens) - total_with_verdict,
        "win_rate": round(wins / total_with_verdict * 100) if total_with_verdict > 0 else None,
        "avg_ath_multiple": round(sum(ath_multiples) / len(ath_multiples), 1) if ath_multiples else None,
        "tokens": tokens,
    }


@router.post("/wallets/compute-pnl/{wallet_address}")
@conditional_rate_limit(READ_RATE_LIMIT)
async def compute_wallet_pnl_endpoint(wallet_address: str, request: Request):
    """
    Compute real PnL for a wallet using per-token-account approach (v2).
    Finds each token account, gets its signatures, parses buy/sell amounts.
    Cost: ~21 credits per token this wallet traded in our database.
    """
    import asyncio
    from meridinate.services.pnl_calculator_v2 import compute_and_store_wallet_pnl_v2
    from meridinate.settings import HELIUS_API_KEY
    from meridinate.credit_tracker import get_credit_tracker

    result = await asyncio.to_thread(
        compute_and_store_wallet_pnl_v2, wallet_address, HELIUS_API_KEY
    )

    get_credit_tracker().record_operation(
        operation="pnl_calculation", label="PnL Calculation",
        credits=result["credits_used"], call_count=1,
        context={"wallet": wallet_address[:12],
                 "tokens": result["tokens_processed"], "updated": result["positions_updated"]},
    )

    return result


@router.post("/wallets/compute-pnl-batch")
@conditional_rate_limit(READ_RATE_LIMIT)
async def compute_batch_pnl(request: Request, limit: int = 20):
    """
    Compute real PnL for top wallets on the leaderboard using v2 per-token-account approach.
    Cost: ~21 credits per wallet-token pair.
    """
    import asyncio
    from meridinate.services.pnl_calculator_v2 import compute_and_store_wallet_pnl_v2
    from meridinate.settings import HELIUS_API_KEY
    from meridinate.credit_tracker import get_credit_tracker

    # Get top wallets by token count, prioritizing those without full coverage
    async with aiosqlite.connect(settings.DATABASE_FILE) as conn:
        cursor = await conn.execute("""
            SELECT ebw.wallet_address, COUNT(DISTINCT ebw.token_id) as token_count
            FROM early_buyer_wallets ebw
            JOIN analyzed_tokens t ON t.id = ebw.token_id
            WHERE (t.deleted_at IS NULL OR t.deleted_at = '')
            GROUP BY ebw.wallet_address
            HAVING token_count >= 2
            ORDER BY token_count DESC
            LIMIT ?
        """, (limit,))
        wallets = [row[0] for row in await cursor.fetchall()]

    results = []
    total_credits = 0

    for addr in wallets:
        try:
            result = await asyncio.to_thread(
                compute_and_store_wallet_pnl_v2, addr, HELIUS_API_KEY
            )
            total_credits += result["credits_used"]
            results.append({
                "wallet": addr,
                "tokens_processed": result["tokens_processed"],
                "tokens_updated": result["positions_updated"],
                "credits": result["credits_used"],
            })
        except Exception as e:
            log_error(f"[PnL Batch] Failed for {addr[:12]}...: {e}")
            results.append({"wallet": addr, "error": str(e)})

    get_credit_tracker().record_operation(
        operation="pnl_batch", label="PnL Batch Calculation",
        credits=total_credits, call_count=len(wallets),
        context={"wallets_processed": len(results)},
    )

    return {
        "wallets_processed": len(results),
        "total_credits": total_credits,
        "results": results,
    }
