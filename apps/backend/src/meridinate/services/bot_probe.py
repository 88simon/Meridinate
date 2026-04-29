"""
Deep Bot Probe — Transaction Collection & FIFO Round-Trip Engine

Collects every transaction for a target bot wallet across all known tokens,
matches buys and sells into FIFO round-trips with cost basis tracking,
and discovers unknown tokens the bot traded outside Meridinate's scan set.

Accounting convention: FIFO (stated, not implied as bot's actual logic).
Two layers stored: token-level aggregates AND round-trip-level behavior.
"""

import json
import sqlite3
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

from meridinate import analyzed_tokens_db as db, settings
from meridinate.observability import log_info, log_error

CHICAGO_TZ = ZoneInfo("America/Chicago")

# DEX program IDs for filtering real trades from noise
DEX_PROGRAM_IDS = {
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",   # PumpFun
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",    # PumpSwap
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Raydium AMM
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",   # Jupiter v6
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",    # Orca Whirlpool
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",   # Meteora DLMM
}

# Minimum SOL to count as a real trade (filter dust/airdrops)
DUST_THRESHOLD_SOL = 0.005


def ensure_probe_tables():
    """Create probe-specific tables if they don't exist."""
    with db.get_db_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bot_probe_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address TEXT NOT NULL,
                phase TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                started_at TEXT,
                completed_at TEXT,
                credits_used INTEGER DEFAULT 0,
                known_tokens_probed INTEGER DEFAULT 0,
                known_tokens_total INTEGER DEFAULT 0,
                unknown_tokens_discovered INTEGER DEFAULT 0,
                transactions_fetched INTEGER DEFAULT 0,
                transactions_parsed INTEGER DEFAULT 0,
                sell_coverage_rate REAL DEFAULT 0,
                round_trip_method TEXT DEFAULT 'FIFO',
                error TEXT,
                coverage_json TEXT
            );

            CREATE TABLE IF NOT EXISTS bot_probe_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                probe_run_id INTEGER,
                wallet_address TEXT NOT NULL,
                token_address TEXT NOT NULL,
                token_name TEXT,
                signature TEXT NOT NULL,
                direction TEXT NOT NULL,
                sol_amount REAL NOT NULL DEFAULT 0,
                token_amount REAL NOT NULL DEFAULT 0,
                timestamp TEXT,
                timestamp_unix INTEGER,
                block_slot INTEGER,
                tip_type TEXT,
                entry_seconds_after_creation REAL,
                position_avg_cost_before REAL,
                position_avg_cost_after REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bot_probe_round_trips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                probe_run_id INTEGER,
                wallet_address TEXT NOT NULL,
                token_address TEXT NOT NULL,
                token_name TEXT,
                entry_sol REAL,
                entry_tokens REAL,
                entry_timestamp TEXT,
                entry_timestamp_unix INTEGER,
                exit_sol REAL,
                exit_tokens REAL,
                exit_timestamp TEXT,
                exit_timestamp_unix INTEGER,
                hold_seconds REAL,
                pnl_sol REAL,
                pnl_multiple REAL,
                trip_type TEXT,
                cost_basis_at_entry REAL,
                cost_basis_at_exit REAL,
                entry_seconds_after_creation REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bot_probe_token_aggregates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                probe_run_id INTEGER,
                wallet_address TEXT NOT NULL,
                token_address TEXT NOT NULL,
                token_name TEXT,
                total_bought_sol REAL DEFAULT 0,
                total_sold_sol REAL DEFAULT 0,
                total_bought_tokens REAL DEFAULT 0,
                total_sold_tokens REAL DEFAULT 0,
                buy_count INTEGER DEFAULT 0,
                sell_count INTEGER DEFAULT 0,
                realized_pnl_sol REAL DEFAULT 0,
                still_holding INTEGER DEFAULT 0,
                remaining_tokens REAL DEFAULT 0,
                round_trip_count INTEGER DEFAULT 0,
                first_buy_timestamp TEXT,
                last_sell_timestamp TEXT,
                tip_types TEXT,
                entry_seconds_after_creation REAL,
                token_birth_timestamp TEXT,
                token_birth_source TEXT,
                in_meridinate_db INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bot_probe_unknown_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                probe_run_id INTEGER,
                wallet_address TEXT NOT NULL,
                token_mint TEXT NOT NULL,
                first_seen_timestamp TEXT,
                direction TEXT,
                sol_amount REAL,
                in_meridinate_db INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS bot_probe_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address TEXT NOT NULL UNIQUE,
                profile_json TEXT NOT NULL,
                comparison_json TEXT,
                total_trades INTEGER,
                win_rate REAL,
                expectancy_sol REAL,
                avg_hold_seconds REAL,
                infrastructure TEXT,
                computed_at TEXT,
                credits_used INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_bpt_wallet ON bot_probe_transactions(wallet_address);
            CREATE INDEX IF NOT EXISTS idx_bpt_token ON bot_probe_transactions(token_address);
            CREATE INDEX IF NOT EXISTS idx_bprt_wallet ON bot_probe_round_trips(wallet_address);
            CREATE INDEX IF NOT EXISTS idx_bpta_wallet ON bot_probe_token_aggregates(wallet_address);
        """)


def _now() -> str:
    return datetime.now(CHICAGO_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")


def _get_token_birth_timestamp(token_address: str) -> Tuple[Optional[str], str]:
    """Get real token birth timestamp, preferring creation events over scan time.
    Returns (timestamp_iso, source)."""
    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        # Try webhook_detections first (real-time creation event)
        cur = conn.execute(
            "SELECT detected_at FROM webhook_detections WHERE token_address = ? ORDER BY detected_at ASC LIMIT 1",
            (token_address,),
        )
        row = cur.fetchone()
        if row and row["detected_at"]:
            return row["detected_at"], "rttf_detection"

        # Try analyzed_tokens creation events
        cur = conn.execute(
            "SELECT first_buy_timestamp, analysis_timestamp FROM analyzed_tokens WHERE token_address = ? LIMIT 1",
            (token_address,),
        )
        row = cur.fetchone()
        if row:
            if row["first_buy_timestamp"]:
                return row["first_buy_timestamp"], "first_buy_event"
            if row["analysis_timestamp"]:
                return row["analysis_timestamp"], "analysis_scan"

    return None, "unknown"


def _fifo_match_round_trips(transactions: List[Dict]) -> Tuple[List[Dict], Dict]:
    """
    Match buys and sells into FIFO round-trips with cost basis tracking.

    Each sell consumes from the earliest unmatched buy inventory.
    Tracks position_avg_cost before and after each leg.

    Returns: (round_trips, aggregate)
    """
    # Sort by timestamp
    sorted_txs = sorted(transactions, key=lambda t: t.get("timestamp_unix") or 0)

    # Inventory queue: [{sol_remaining, tokens_remaining, sol_per_token, timestamp, timestamp_unix}]
    inventory = []
    round_trips = []
    total_bought_sol = 0.0
    total_sold_sol = 0.0
    total_bought_tokens = 0.0
    total_sold_tokens = 0.0
    buy_count = 0
    sell_count = 0
    tip_types_seen = set()

    for tx in sorted_txs:
        if tx.get("tip_type"):
            tip_types_seen.add(tx["tip_type"])

        # Compute position avg cost BEFORE this leg
        total_inv_tokens = sum(lot["tokens_remaining"] for lot in inventory)
        total_inv_sol = sum(lot["sol_remaining"] for lot in inventory)
        avg_cost_before = total_inv_sol / total_inv_tokens if total_inv_tokens > 0 else 0

        if tx["direction"] == "buy":
            sol = tx.get("sol_amount", 0)
            tokens = tx.get("token_amount", 0)
            if tokens > 0:
                inventory.append({
                    "sol_remaining": sol,
                    "tokens_remaining": tokens,
                    "sol_per_token": sol / tokens if tokens > 0 else 0,
                    "timestamp": tx.get("timestamp"),
                    "timestamp_unix": tx.get("timestamp_unix"),
                })
                total_bought_sol += sol
                total_bought_tokens += tokens
                buy_count += 1

            # Cost after
            total_inv_tokens_after = sum(lot["tokens_remaining"] for lot in inventory)
            total_inv_sol_after = sum(lot["sol_remaining"] for lot in inventory)
            avg_cost_after = total_inv_sol_after / total_inv_tokens_after if total_inv_tokens_after > 0 else 0

            tx["position_avg_cost_before"] = round(avg_cost_before, 12)
            tx["position_avg_cost_after"] = round(avg_cost_after, 12)

        elif tx["direction"] == "sell":
            sell_tokens_remaining = tx.get("token_amount", 0)
            sell_sol = tx.get("sol_amount", 0)
            sell_sol_per_token = sell_sol / sell_tokens_remaining if sell_tokens_remaining > 0 else 0
            total_sold_sol += sell_sol
            total_sold_tokens += sell_tokens_remaining
            sell_count += 1

            # FIFO matching: consume from earliest inventory lots
            while sell_tokens_remaining > 0 and inventory:
                lot = inventory[0]
                consumed = min(sell_tokens_remaining, lot["tokens_remaining"])
                if consumed <= 0:
                    inventory.pop(0)
                    continue

                # Proportional SOL for this consumed portion
                entry_sol = lot["sol_per_token"] * consumed
                exit_sol = sell_sol_per_token * consumed

                entry_ts_unix = lot.get("timestamp_unix") or 0
                exit_ts_unix = tx.get("timestamp_unix") or 0
                hold = (exit_ts_unix - entry_ts_unix) if entry_ts_unix and exit_ts_unix else None

                pnl = exit_sol - entry_sol
                pnl_mult = exit_sol / entry_sol if entry_sol > 0 else 0

                trip_type = "full" if consumed >= lot["tokens_remaining"] else "partial"

                round_trips.append({
                    "entry_sol": round(entry_sol, 9),
                    "entry_tokens": round(consumed, 6),
                    "entry_timestamp": lot.get("timestamp"),
                    "entry_timestamp_unix": lot.get("timestamp_unix"),
                    "exit_sol": round(exit_sol, 9),
                    "exit_tokens": round(consumed, 6),
                    "exit_timestamp": tx.get("timestamp"),
                    "exit_timestamp_unix": tx.get("timestamp_unix"),
                    "hold_seconds": hold,
                    "pnl_sol": round(pnl, 9),
                    "pnl_multiple": round(pnl_mult, 4),
                    "trip_type": trip_type,
                    "cost_basis_at_entry": round(lot["sol_per_token"], 12),
                    "cost_basis_at_exit": round(sell_sol_per_token, 12),
                })

                lot["tokens_remaining"] -= consumed
                lot["sol_remaining"] -= entry_sol
                sell_tokens_remaining -= consumed

                if lot["tokens_remaining"] <= 0:
                    inventory.pop(0)

            # Cost after
            total_inv_tokens_after = sum(lot["tokens_remaining"] for lot in inventory)
            total_inv_sol_after = sum(lot["sol_remaining"] for lot in inventory)
            avg_cost_after = total_inv_sol_after / total_inv_tokens_after if total_inv_tokens_after > 0 else 0

            tx["position_avg_cost_before"] = round(avg_cost_before, 12)
            tx["position_avg_cost_after"] = round(avg_cost_after, 12)

    remaining_tokens = sum(lot["tokens_remaining"] for lot in inventory)

    aggregate = {
        "total_bought_sol": round(total_bought_sol, 9),
        "total_sold_sol": round(total_sold_sol, 9),
        "total_bought_tokens": round(total_bought_tokens, 6),
        "total_sold_tokens": round(total_sold_tokens, 6),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "realized_pnl_sol": round(total_sold_sol - total_bought_sol, 9),
        "still_holding": remaining_tokens > 0,
        "remaining_tokens": round(remaining_tokens, 6),
        "round_trip_count": len(round_trips),
        "tip_types": ",".join(sorted(tip_types_seen)) if tip_types_seen else None,
    }

    return round_trips, aggregate


def _probe_via_token_mint(
    wallet_address: str,
    token_address: str,
    api_key: str,
    max_signatures: int = 200,
) -> Tuple[List[Dict], int]:
    """
    Fallback: scan signatures on the token mint address and filter for
    transactions involving our target wallet. More expensive but works
    when token accounts are closed and the trade is too old for the
    main wallet preload.

    Returns (transactions, credits_used).
    """
    from meridinate.helius_api import HeliusAPI
    helius = HeliusAPI(api_key)
    credits_used = 0
    transactions = []

    try:
        signatures = helius._rpc_call(
            "getSignaturesForAddress",
            [token_address, {"limit": max_signatures}]
        ) or []
        credits_used += 1
    except Exception:
        return [], credits_used

    for sig_obj in signatures:
        sig = sig_obj.get("signature")
        if not sig:
            continue

        try:
            tx_data = helius._rpc_call(
                "getTransaction",
                [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
            )
            credits_used += 1

            if not tx_data or not isinstance(tx_data, dict):
                continue

            # Quick check: is our wallet in the account keys at all?
            account_keys = tx_data.get("transaction", {}).get("message", {}).get("accountKeys", [])
            wallet_in_keys = any(
                (ak.get("pubkey", ak) if isinstance(ak, dict) else ak) == wallet_address
                for ak in account_keys
            )
            if not wallet_in_keys:
                continue

            # Parse timestamp
            parsed = helius._parse_rpc_transaction(tx_data, sig)
            timestamp = parsed.get("timestamp") if parsed else None
            timestamp_unix = None
            if timestamp:
                ts_str = str(timestamp)
                if ts_str.isdigit():
                    timestamp_unix = int(ts_str)
                else:
                    try:
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        timestamp_unix = int(dt.timestamp())
                    except (ValueError, TypeError):
                        pass

            block_slot = tx_data.get("slot")

            # Tip detection
            tip_type = None
            if parsed:
                try:
                    from meridinate.services.tip_detector import detect_tips_in_parsed_tx
                    tip_type = detect_tips_in_parsed_tx(parsed)
                except Exception:
                    pass

            # Compute balance changes
            pre_sol_list = meta.get("preBalances", [])
            post_sol_list = meta.get("postBalances", [])

            # Find which account index is our wallet
            account_keys = tx_data.get("transaction", {}).get("message", {}).get("accountKeys", [])
            wallet_idx = None
            for idx, ak in enumerate(account_keys):
                key = ak.get("pubkey", ak) if isinstance(ak, dict) else ak
                if key == wallet_address:
                    wallet_idx = idx
                    break

            sol_change = 0
            if wallet_idx is not None and wallet_idx < len(pre_sol_list) and wallet_idx < len(post_sol_list):
                sol_change = (post_sol_list[wallet_idx] - pre_sol_list[wallet_idx]) / 1e9

            pre_amt = 0
            post_amt = 0
            for b in pre_balances:
                if b.get("owner") == wallet_address and b.get("mint") == token_address:
                    pre_amt = float(b.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
            for b in post_balances:
                if b.get("owner") == wallet_address and b.get("mint") == token_address:
                    post_amt = float(b.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)

            token_delta = post_amt - pre_amt
            if abs(token_delta) < 0.001:
                continue

            is_buy = token_delta > 0
            sol_amount = abs(sol_change)

            if sol_amount < DUST_THRESHOLD_SOL:
                continue

            transactions.append({
                "signature": sig,
                "direction": "buy" if is_buy else "sell",
                "sol_amount": sol_amount,
                "token_amount": abs(token_delta),
                "timestamp": timestamp,
                "timestamp_unix": timestamp_unix,
                "block_slot": block_slot,
                "tip_type": tip_type,
            })

        except Exception:
            continue

    return transactions, credits_used


def probe_wallet_token(
    wallet_address: str,
    token_address: str,
    api_key: str,
    max_signatures: int = 200,
    preloaded_main_txs: List[Dict] = None,
) -> Dict[str, Any]:
    """
    Collect all transactions for a wallet on a specific token.
    Returns raw transactions with cost basis tracking per leg.

    Uses token account signatures when available. Falls back to
    preloaded main wallet transactions when token account is closed
    (bot reclaimed rent SOL).
    """
    from meridinate.helius_api import HeliusAPI

    helius = HeliusAPI(api_key)
    credits_used = 0
    transactions = []

    # Step 1: Try to find the wallet's token account
    token_accounts, ta_credits = helius.get_token_accounts_by_owner(wallet_address, token_address)
    credits_used += ta_credits

    signatures = []
    if token_accounts:
        token_account_pubkey = token_accounts[0].get("pubkey")
        if token_account_pubkey:
            # Step 2a: Get signatures via token account (preferred — most complete)
            try:
                signatures = helius._rpc_call(
                    "getSignaturesForAddress",
                    [token_account_pubkey, {"limit": max_signatures}]
                ) or []
                credits_used += 1
            except Exception:
                signatures = []

    if not signatures:
        # Fallback: use preloaded main wallet transactions filtered for this token
        # This happens when the bot closed the token account after selling
        if preloaded_main_txs:
            # Filter preloaded txs for this token mint
            for ptx in preloaded_main_txs:
                if ptx.get("token_address") == token_address:
                    transactions.append(ptx)
            return {"transactions": transactions, "credits_used": credits_used, "method": "preloaded_fallback"}

        # No token account AND no preloaded data — try main wallet signatures directly
        try:
            signatures = helius._rpc_call(
                "getSignaturesForAddress",
                [wallet_address, {"limit": max_signatures}]
            ) or []
            credits_used += 1
        except Exception:
            return {"transactions": [], "credits_used": credits_used, "error": "no_token_account_and_main_sig_failed"}

    if not signatures:
        return {"transactions": [], "credits_used": credits_used}

    # Step 3: Parse each transaction
    for sig_obj in signatures:
        sig = sig_obj.get("signature")
        if not sig:
            continue

        try:
            tx_data = helius._rpc_call(
                "getTransaction",
                [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
            )
            credits_used += 1

            if not tx_data:
                continue

            parsed = helius._parse_rpc_transaction(tx_data, sig)
            if not parsed:
                continue

            # Detect tip infrastructure per transaction
            tip_type = None
            try:
                from meridinate.services.tip_detector import detect_tips_in_parsed_tx
                tip_type = detect_tips_in_parsed_tx(parsed)
            except Exception:
                pass

            # Extract block slot
            block_slot = None
            if isinstance(tx_data, dict):
                block_slot = tx_data.get("slot")

            timestamp = parsed.get("timestamp")
            timestamp_unix = None
            if timestamp:
                try:
                    ts_str = str(timestamp)
                    if ts_str.isdigit():
                        timestamp_unix = int(ts_str)
                    else:
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        timestamp_unix = int(dt.timestamp())
                except (ValueError, TypeError):
                    pass

            # Use pre/post token balances — works for ALL DEX types
            meta = tx_data.get("meta", {}) if isinstance(tx_data, dict) else {}
            pre_balances = meta.get("preTokenBalances", [])
            post_balances = meta.get("postTokenBalances", [])
            pre_sol_list = meta.get("preBalances", [])
            post_sol_list = meta.get("postBalances", [])
            sol_change = (post_sol_list[0] - pre_sol_list[0]) / 1e9 if pre_sol_list and post_sol_list else 0

            # Find wallet's balance change for the target token
            pre_amt = 0
            post_amt = 0
            for b in pre_balances:
                if b.get("owner") == wallet_address and b.get("mint") == token_address:
                    pre_amt = float(b.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
            for b in post_balances:
                if b.get("owner") == wallet_address and b.get("mint") == token_address:
                    post_amt = float(b.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)

            token_delta = post_amt - pre_amt
            if abs(token_delta) < 0.001:
                continue

            is_buy = token_delta > 0
            sol_amount = abs(sol_change)

            transactions.append({
                "signature": sig,
                "direction": "buy" if is_buy else "sell",
                "sol_amount": sol_amount,
                "token_amount": abs(token_delta),
                "timestamp": timestamp,
                "timestamp_unix": timestamp_unix,
                "block_slot": block_slot,
                "tip_type": tip_type,
            })

        except Exception:
            continue

    return {
        "transactions": transactions,
        "credits_used": credits_used,
        "signatures_fetched": len(signatures),
    }


def run_phase1_full_transactions(
    wallet_address: str,
    on_progress=None,
) -> Dict[str, Any]:
    """
    Phase 1: Collect full transaction history for all known tokens.
    Builds FIFO round-trips and token-level aggregates.

    Returns probe run summary.
    """
    ensure_probe_tables()
    api_key = settings.HELIUS_API_KEY

    # Create probe run
    now = _now()
    with db.get_db_connection() as conn:
        cur = conn.execute(
            "INSERT INTO bot_probe_runs (wallet_address, phase, status, started_at) VALUES (?, 'phase1_transactions', 'running', ?)",
            (wallet_address, now),
        )
        run_id = cur.lastrowid

    # Get all known tokens for this wallet
    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT DISTINCT ebw.token_id, at.token_address, at.token_name
            FROM early_buyer_wallets ebw
            JOIN analyzed_tokens at ON at.id = ebw.token_id
            WHERE ebw.wallet_address = ? AND (at.deleted_at IS NULL OR at.deleted_at = '')
            ORDER BY at.analysis_timestamp DESC
        """, (wallet_address,)).fetchall()
        known_tokens = [dict(r) for r in rows]

    total_tokens = len(known_tokens)
    total_credits = 0
    tokens_with_sells = 0
    total_txs_fetched = 0
    total_txs_parsed = 0
    total_round_trips = 0

    log_info(f"[BotProbe] Phase 1 starting: {wallet_address[:16]}... — {total_tokens} tokens")

    # Preload main wallet transactions for fallback (covers closed token accounts)
    # This is essential for bots that close token accounts after selling
    if on_progress:
        on_progress(0, total_tokens, "Preloading main wallet transactions...", 0)

    preloaded_by_token = {}  # token_address -> [tx, tx, ...]
    known_token_addrs = {t["token_address"] for t in known_tokens}
    try:
        from meridinate.helius_api import HeliusAPI
        helius = HeliusAPI(api_key)

        # Paginated fetch-and-parse: fetch one page of sigs, parse immediately,
        # stop when we've found all known tokens or hit max pages
        before_sig = None
        max_pages = 20
        tokens_found_so_far = set()
        total_sigs_processed = 0

        for page in range(max_pages):
            params = {"limit": 1000}
            if before_sig:
                params["before"] = before_sig
            page_sigs = helius._rpc_call(
                "getSignaturesForAddress",
                [wallet_address, params]
            ) or []
            total_credits += 1

            if not page_sigs:
                break

            before_sig = page_sigs[-1].get("signature")

            if on_progress:
                on_progress(0, total_tokens,
                    f"Preloading: page {page+1}, parsing {len(page_sigs)} sigs "
                    f"({len(tokens_found_so_far)}/{len(known_token_addrs)} tokens found)...",
                    total_credits)

            # Parse this page immediately
            for sig_obj in page_sigs:
                sig = sig_obj.get("signature")
                if not sig:
                    continue
                total_sigs_processed += 1
                try:
                    tx_data = helius._rpc_call(
                        "getTransaction",
                        [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
                    )
                    total_credits += 1
                    if not tx_data:
                        continue

                    parsed = helius._parse_rpc_transaction(tx_data, sig)
                    if not parsed:
                        continue

                    # Detect tip
                    tip_type = None
                    try:
                        from meridinate.services.tip_detector import detect_tips_in_parsed_tx
                        tip_type = detect_tips_in_parsed_tx(parsed)
                    except Exception:
                        pass

                    block_slot = tx_data.get("slot") if isinstance(tx_data, dict) else None
                    timestamp = parsed.get("timestamp")
                    timestamp_unix = None
                    if timestamp:
                        try:
                            ts_str = str(timestamp)
                            if ts_str.isdigit():
                                timestamp_unix = int(ts_str)
                            else:
                                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                timestamp_unix = int(dt.timestamp())
                        except (ValueError, TypeError):
                            pass

                    # Use pre/post token balances — works for ALL DEX types
                    meta = tx_data.get("meta", {}) if isinstance(tx_data, dict) else {}
                    pre_balances = meta.get("preTokenBalances", [])
                    post_balances = meta.get("postTokenBalances", [])
                    pre_sol_list = meta.get("preBalances", [])
                    post_sol_list = meta.get("postBalances", [])
                    sol_change = (post_sol_list[0] - pre_sol_list[0]) / 1e9 if pre_sol_list and post_sol_list else 0

                    # Find all mints this wallet held
                    wallet_mints = set()
                    for b in pre_balances + post_balances:
                        if b.get("owner") == wallet_address and b.get("mint"):
                            wallet_mints.add(b.get("mint"))

                    for mint in wallet_mints:
                        pre_amt = 0
                        post_amt = 0
                        for b in pre_balances:
                            if b.get("owner") == wallet_address and b.get("mint") == mint:
                                pre_amt = float(b.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                        for b in post_balances:
                            if b.get("owner") == wallet_address and b.get("mint") == mint:
                                post_amt = float(b.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)

                        token_delta = post_amt - pre_amt
                        if abs(token_delta) < 0.001:
                            continue

                        is_buy = token_delta > 0
                        sol_amount = abs(sol_change)
                        if sol_amount < DUST_THRESHOLD_SOL:
                            continue

                        tx_record = {
                            "signature": sig,
                            "direction": "buy" if is_buy else "sell",
                            "sol_amount": sol_amount,
                            "token_amount": abs(token_delta),
                            "timestamp": timestamp,
                            "timestamp_unix": timestamp_unix,
                            "block_slot": block_slot,
                            "tip_type": tip_type,
                            "token_address": mint,
                        }

                        if mint not in preloaded_by_token:
                            preloaded_by_token[mint] = []
                        preloaded_by_token[mint].append(tx_record)
                        if mint in known_token_addrs:
                            tokens_found_so_far.add(mint)

                except Exception:
                    continue

                time.sleep(0.05)

                # Check if we've found all known tokens — stop early
                if len(tokens_found_so_far) >= len(known_token_addrs):
                    log_info(f"[BotProbe] Preload: found all {len(known_token_addrs)} known tokens, stopping early")
                    break

            # End of page loop
            if len(tokens_found_so_far) >= len(known_token_addrs):
                break

            time.sleep(0.1)

        preloaded_count = sum(len(v) for v in preloaded_by_token.values())
        log_info(f"[BotProbe] Preloaded {preloaded_count} transactions across {len(preloaded_by_token)} tokens "
                 f"from {total_sigs_processed} main wallet sigs ({total_credits} credits)")
    except Exception as e:
        log_error(f"[BotProbe] Preload failed (continuing without fallback): {e}")

    for i, token_info in enumerate(known_tokens):
        token_addr = token_info["token_address"]
        token_name = token_info.get("token_name", "unknown")

        if on_progress:
            on_progress(i + 1, total_tokens, token_name, total_credits)

        # Strategy: try 3 methods in order of cost/reliability
        # 1. Preloaded main wallet txs (free — already fetched)
        # 2. Token account probe (works when account still open)
        # 3. Token mint signatures (fallback for closed accounts + old trades)
        transactions = []

        # Method 1: Preloaded
        preloaded_txs = preloaded_by_token.get(token_addr, [])
        if preloaded_txs:
            transactions = preloaded_txs

        # Method 2: Token account probe
        if not transactions:
            result = probe_wallet_token(
                wallet_address, token_addr, api_key, max_signatures=200,
            )
            total_credits += result.get("credits_used", 0)
            total_txs_fetched += result.get("signatures_fetched", 0)
            transactions = result.get("transactions", [])

        # Method 3: Scan token mint signatures for this wallet's activity
        if not transactions:
            mint_txs, mint_credits = _probe_via_token_mint(
                wallet_address, token_addr, api_key, max_signatures=200,
            )
            total_credits += mint_credits
            transactions = mint_txs
            if mint_txs:
                log_info(f"[BotProbe] Mint fallback found {len(mint_txs)} txs for {token_name}")

        if not transactions:
            continue

        total_txs_parsed += len(transactions)

        # Get token birth timestamp
        birth_ts, birth_source = _get_token_birth_timestamp(token_addr)

        # Compute entry timing relative to birth
        for tx in transactions:
            tx["entry_seconds_after_creation"] = None
            if birth_ts and tx.get("timestamp"):
                try:
                    birth_dt = datetime.fromisoformat(str(birth_ts).replace("Z", "+00:00"))
                    tx_dt = datetime.fromisoformat(str(tx["timestamp"]).replace("Z", "+00:00"))
                    delta = (tx_dt - birth_dt).total_seconds()
                    if delta >= 0:
                        tx["entry_seconds_after_creation"] = round(delta, 1)
                except (ValueError, TypeError):
                    pass

        # FIFO round-trip matching
        round_trips, aggregate = _fifo_match_round_trips(transactions)
        total_round_trips += len(round_trips)

        if aggregate["sell_count"] > 0:
            tokens_with_sells += 1

        # Store transactions
        with db.get_db_connection() as conn:
            for tx in transactions:
                conn.execute("""
                    INSERT INTO bot_probe_transactions
                    (probe_run_id, wallet_address, token_address, token_name, signature,
                     direction, sol_amount, token_amount, timestamp, timestamp_unix,
                     block_slot, tip_type, entry_seconds_after_creation,
                     position_avg_cost_before, position_avg_cost_after)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id, wallet_address, token_addr, token_name, tx["signature"],
                    tx["direction"], tx["sol_amount"], tx["token_amount"],
                    tx.get("timestamp"), tx.get("timestamp_unix"),
                    tx.get("block_slot"), tx.get("tip_type"),
                    tx.get("entry_seconds_after_creation"),
                    tx.get("position_avg_cost_before"),
                    tx.get("position_avg_cost_after"),
                ))

            # Store round trips
            for rt in round_trips:
                conn.execute("""
                    INSERT INTO bot_probe_round_trips
                    (probe_run_id, wallet_address, token_address, token_name,
                     entry_sol, entry_tokens, entry_timestamp, entry_timestamp_unix,
                     exit_sol, exit_tokens, exit_timestamp, exit_timestamp_unix,
                     hold_seconds, pnl_sol, pnl_multiple, trip_type,
                     cost_basis_at_entry, cost_basis_at_exit,
                     entry_seconds_after_creation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id, wallet_address, token_addr, token_name,
                    rt["entry_sol"], rt["entry_tokens"],
                    rt["entry_timestamp"], rt.get("entry_timestamp_unix"),
                    rt["exit_sol"], rt["exit_tokens"],
                    rt["exit_timestamp"], rt.get("exit_timestamp_unix"),
                    rt.get("hold_seconds"), rt["pnl_sol"], rt["pnl_multiple"],
                    rt["trip_type"], rt["cost_basis_at_entry"], rt["cost_basis_at_exit"],
                    transactions[0].get("entry_seconds_after_creation") if transactions else None,
                ))

            # Store token aggregate
            first_buy_ts = None
            last_sell_ts = None
            buys = [t for t in transactions if t["direction"] == "buy"]
            sells = [t for t in transactions if t["direction"] == "sell"]
            if buys:
                first_buy_ts = min(t.get("timestamp") or "" for t in buys) or None
            if sells:
                last_sell_ts = max(t.get("timestamp") or "" for t in sells) or None

            entry_secs = None
            if buys and buys[0].get("entry_seconds_after_creation") is not None:
                entry_secs = buys[0]["entry_seconds_after_creation"]

            conn.execute("""
                INSERT INTO bot_probe_token_aggregates
                (probe_run_id, wallet_address, token_address, token_name,
                 total_bought_sol, total_sold_sol, total_bought_tokens, total_sold_tokens,
                 buy_count, sell_count, realized_pnl_sol, still_holding, remaining_tokens,
                 round_trip_count, first_buy_timestamp, last_sell_timestamp,
                 tip_types, entry_seconds_after_creation,
                 token_birth_timestamp, token_birth_source, in_meridinate_db)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                run_id, wallet_address, token_addr, token_name,
                aggregate["total_bought_sol"], aggregate["total_sold_sol"],
                aggregate["total_bought_tokens"], aggregate["total_sold_tokens"],
                aggregate["buy_count"], aggregate["sell_count"],
                aggregate["realized_pnl_sol"],
                1 if aggregate["still_holding"] else 0,
                aggregate["remaining_tokens"],
                aggregate["round_trip_count"],
                first_buy_ts, last_sell_ts,
                aggregate["tip_types"], entry_secs,
                birth_ts, birth_source,
            ))

        # Rate limiting
        time.sleep(0.3)

    # Update probe run
    sell_coverage = tokens_with_sells / max(total_tokens, 1)
    coverage = {
        "known_tokens_probed": total_tokens,
        "tokens_with_sells": tokens_with_sells,
        "total_transactions": total_txs_parsed,
        "total_round_trips": total_round_trips,
        "sell_coverage_rate": round(sell_coverage, 3),
    }

    with db.get_db_connection() as conn:
        conn.execute("""
            UPDATE bot_probe_runs SET
                status = 'completed', completed_at = ?,
                credits_used = ?, known_tokens_probed = ?, known_tokens_total = ?,
                transactions_fetched = ?, transactions_parsed = ?,
                sell_coverage_rate = ?, coverage_json = ?
            WHERE id = ?
        """, (
            _now(), total_credits, total_tokens, total_tokens,
            total_txs_fetched, total_txs_parsed,
            sell_coverage, json.dumps(coverage),
            run_id,
        ))

    log_info(
        f"[BotProbe] Phase 1 complete: {wallet_address[:16]}... — "
        f"{total_tokens} tokens, {total_txs_parsed} txs, {total_round_trips} round-trips, "
        f"{total_credits} credits, {sell_coverage:.0%} sell coverage"
    )

    return {
        "run_id": run_id,
        "wallet_address": wallet_address,
        "phase": "phase1_transactions",
        "tokens_probed": total_tokens,
        "transactions_parsed": total_txs_parsed,
        "round_trips": total_round_trips,
        "credits_used": total_credits,
        "sell_coverage": sell_coverage,
        "coverage": coverage,
    }


def run_phase2_discover_unknown_tokens(
    wallet_address: str,
    max_main_signatures: int = 500,
    on_progress=None,
) -> Dict[str, Any]:
    """
    Phase 2: Discover tokens the bot traded that Meridinate never scanned.
    Scans main wallet signatures and extracts token mints from swap transactions.
    """
    ensure_probe_tables()
    api_key = settings.HELIUS_API_KEY
    from meridinate.helius_api import HeliusAPI
    helius = HeliusAPI(api_key)

    now = _now()
    with db.get_db_connection() as conn:
        cur = conn.execute(
            "INSERT INTO bot_probe_runs (wallet_address, phase, status, started_at) VALUES (?, 'phase2_discovery', 'running', ?)",
            (wallet_address, now),
        )
        run_id = cur.lastrowid

    credits_used = 0

    # Get all token mints we already know about
    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT DISTINCT token_address FROM bot_probe_token_aggregates WHERE wallet_address = ?",
                            (wallet_address,)).fetchall()
        known_mints = {r["token_address"] for r in rows}
        # Also include tokens from early_buyer_wallets
        rows2 = conn.execute("""
            SELECT DISTINCT at.token_address FROM early_buyer_wallets ebw
            JOIN analyzed_tokens at ON at.id = ebw.token_id
            WHERE ebw.wallet_address = ?
        """, (wallet_address,)).fetchall()
        known_mints.update(r["token_address"] for r in rows2)

    # Get main wallet signatures
    try:
        signatures = helius._rpc_call(
            "getSignaturesForAddress",
            [wallet_address, {"limit": max_main_signatures}]
        )
        credits_used += 1
    except Exception as e:
        log_error(f"[BotProbe] Phase 2 failed to get main wallet sigs: {e}")
        with db.get_db_connection() as conn:
            conn.execute("UPDATE bot_probe_runs SET status = 'failed', error = ? WHERE id = ?",
                         (str(e), run_id))
        return {"run_id": run_id, "error": str(e), "credits_used": credits_used}

    unknown_mints = {}  # mint -> {first_seen, direction, sol_amount}
    txs_parsed = 0

    for i, sig_obj in enumerate(signatures or []):
        sig = sig_obj.get("signature")
        if not sig:
            continue

        if on_progress and i % 50 == 0:
            on_progress(i, len(signatures), credits_used)

        try:
            tx_data = helius._rpc_call(
                "getTransaction",
                [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
            )
            credits_used += 1
            txs_parsed += 1

            if not tx_data:
                continue

            parsed = helius._parse_rpc_transaction(tx_data, sig)
            if not parsed:
                continue

            # Check if this involves a DEX program
            program_ids = set()
            if isinstance(tx_data, dict):
                for ix in (tx_data.get("transaction", {}).get("message", {}).get("instructions", [])):
                    pid = ix.get("programId", "")
                    if pid:
                        program_ids.add(pid)
                # Also inner instructions
                for inner_list in (tx_data.get("meta", {}).get("innerInstructions", []) or []):
                    for ix in inner_list.get("instructions", []):
                        pid = ix.get("programId", "")
                        if pid:
                            program_ids.add(pid)

            is_dex_tx = bool(program_ids & DEX_PROGRAM_IDS)
            if not is_dex_tx:
                continue

            # Extract token mints from transfers
            for tt in parsed.get("tokenTransfers", []):
                mint = tt.get("mint")
                if not mint or mint in known_mints:
                    continue

                token_amount = tt.get("tokenAmount", 0)
                if token_amount <= 0:
                    continue

                is_buy = tt.get("toUserAccount") == wallet_address
                is_sell = tt.get("fromUserAccount") == wallet_address
                if not is_buy and not is_sell:
                    continue

                # Check SOL flow for dust filtering
                sol_amount = 0
                for nt in parsed.get("nativeTransfers", []):
                    amt = nt.get("amount", 0)
                    if amt <= 100000:
                        continue
                    if is_buy and nt.get("fromUserAccount") == wallet_address:
                        sol_amount = max(sol_amount, amt / 1e9)
                    elif is_sell and nt.get("toUserAccount") == wallet_address:
                        sol_amount = max(sol_amount, amt / 1e9)

                if sol_amount < DUST_THRESHOLD_SOL:
                    continue

                if mint not in unknown_mints:
                    unknown_mints[mint] = {
                        "first_seen": parsed.get("timestamp"),
                        "direction": "buy" if is_buy else "sell",
                        "sol_amount": sol_amount,
                    }

        except Exception:
            continue

        time.sleep(0.1)

    # Check which unknown mints are in Meridinate's DB
    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        for mint, info in unknown_mints.items():
            in_db = conn.execute(
                "SELECT 1 FROM analyzed_tokens WHERE token_address = ? LIMIT 1", (mint,)
            ).fetchone()
            conn.execute("""
                INSERT INTO bot_probe_unknown_tokens
                (probe_run_id, wallet_address, token_mint, first_seen_timestamp, direction, sol_amount, in_meridinate_db)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (run_id, wallet_address, mint, info["first_seen"],
                  info["direction"], info["sol_amount"], 1 if in_db else 0))

    # Update run
    with db.get_db_connection() as conn:
        conn.execute("""
            UPDATE bot_probe_runs SET
                status = 'completed', completed_at = ?,
                credits_used = ?, unknown_tokens_discovered = ?,
                transactions_fetched = ?, transactions_parsed = ?,
                coverage_json = ?
            WHERE id = ?
        """, (
            _now(), credits_used, len(unknown_mints), len(signatures or []), txs_parsed,
            json.dumps({"unknown_mints": len(unknown_mints), "main_sigs_scanned": len(signatures or []),
                        "dex_txs_with_unknown_tokens": len(unknown_mints)}),
            run_id,
        ))

    log_info(
        f"[BotProbe] Phase 2 complete: {wallet_address[:16]}... — "
        f"scanned {len(signatures or [])} main sigs, found {len(unknown_mints)} unknown token mints, "
        f"{credits_used} credits"
    )

    return {
        "run_id": run_id,
        "wallet_address": wallet_address,
        "phase": "phase2_discovery",
        "main_signatures_scanned": len(signatures or []),
        "unknown_tokens_discovered": len(unknown_mints),
        "credits_used": credits_used,
    }
