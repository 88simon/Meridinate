"""
Wallet Leaderboard Cache

Pre-computes wallet statistics into cache tables for instant filtered queries.
Rebuild is triggered after MC tracker and position checker jobs (~200-500ms for 6k wallets).
The API endpoint queries these tables with SQL instead of aggregating in Python per request.
"""

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_error, log_info

_rebuild_lock = threading.Lock()
_last_rebuild_at: float = 0

# Tier score weights (same as in leaderboard router)
TIER_SCORE_WEIGHTS = {
    "win:100x": 100, "win:50x": 50, "win:25x": 25,
    "win:10x": 10, "win:5x": 5, "win:3x": 3,
    "loss:rug": -5, "loss:90": -3, "loss:70": -2,
    "loss:dead": -4, "loss:stale": -1,
}

HOME_RUN_TIERS = {"win:100x", "win:50x", "win:25x", "win:10x"}
RUG_TIERS = {"loss:rug", "loss:dead"}


def rebuild_leaderboard_cache() -> Dict[str, Any]:
    """
    Full rebuild of wallet_leaderboard_cache + wallet_leaderboard_tags + wallet_leaderboard_tiers.
    Pure DB computation, zero Helius credits.
    Uses a lock to prevent concurrent rebuilds from MC tracker + position checker racing.
    """
    global _last_rebuild_at

    # Skip if rebuilt within the last 10 seconds (debounce concurrent triggers)
    if time.time() - _last_rebuild_at < 10:
        return {"wallets_cached": 0, "duration_ms": 0, "skipped": "rebuilt_recently"}

    if not _rebuild_lock.acquire(blocking=False):
        return {"wallets_cached": 0, "duration_ms": 0, "skipped": "rebuild_in_progress"}

    t0 = time.time()
    result = {"wallets_cached": 0, "duration_ms": 0}

    try:
        with db.get_db_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)

            # ============================================================
            # Phase 1: Fetch all source data in bulk
            # ============================================================

            # 1a. All wallet-token rows with MC performance
            cursor.execute("""
                SELECT
                    ebw.wallet_address,
                    ebw.token_id,
                    ebw.total_usd,
                    ebw.wallet_balance_usd,
                    ebw.avg_entry_seconds,
                    t.market_cap_usd as analysis_mc,
                    t.market_cap_usd_current as current_mc,
                    t.analysis_timestamp,
                    t.token_name,
                    (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = ebw.token_id
                     AND tt.tag IN ('verified-win', 'verified-loss') LIMIT 1) as verdict
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens t ON t.id = ebw.token_id
                    AND (t.deleted_at IS NULL OR t.deleted_at = '')
            """)
            all_rows = cursor.fetchall()

            # 1b. PnL data from mtew_token_positions
            cursor.execute("""
                SELECT wallet_address, token_id, realized_pnl, still_holding,
                       total_bought_usd, current_balance_usd,
                       COALESCE(pnl_source, 'estimated') as pnl_source
                FROM mtew_token_positions
            """)
            pnl_rows = {}
            for r in cursor.fetchall():
                realized = r[2] or 0
                still_holding = r[3]
                bought = r[4] or 0
                current_usd = r[5] or 0
                source = r[6]
                unrealized = (current_usd - bought) if still_holding else 0
                pnl_rows[(r[0], r[1])] = {
                    "pnl": realized + unrealized, "realized": realized,
                    "unrealized": unrealized, "source": source,
                }

            # 1c. Wallet tags
            cursor.execute("SELECT wallet_address, GROUP_CONCAT(tag) FROM wallet_tags GROUP BY wallet_address")
            wallet_tags_map: Dict[str, List[str]] = {}
            for r in cursor.fetchall():
                wallet_tags_map[r[0]] = r[1].split(",") if r[1] else []

            # 1d. Per-wallet win/loss tier counts from token_tags
            cursor.execute("""
                SELECT ebw.wallet_address, tt.tag, COUNT(*) as cnt
                FROM early_buyer_wallets ebw
                JOIN token_tags tt ON tt.token_id = ebw.token_id
                JOIN analyzed_tokens t ON t.id = ebw.token_id
                    AND (t.deleted_at IS NULL OR t.deleted_at = '')
                WHERE tt.tag LIKE 'win:%' OR tt.tag LIKE 'loss:%'
                GROUP BY ebw.wallet_address, tt.tag
            """)
            wallet_tiers: Dict[str, Dict[str, int]] = {}
            for r in cursor.fetchall():
                addr, tag, cnt = r[0], r[1], r[2]
                if addr not in wallet_tiers:
                    wallet_tiers[addr] = {}
                wallet_tiers[addr][tag] = cnt

            # 1e. Wallet creation dates from enrichment cache
            cursor.execute(
                "SELECT wallet_address, funded_by_json FROM wallet_enrichment_cache WHERE funded_by_json IS NOT NULL"
            )
            wallet_created_map: Dict[str, str] = {}
            for r in cursor.fetchall():
                try:
                    fb = json.loads(r[1])
                    if isinstance(fb, dict) and fb.get("date"):
                        wallet_created_map[r[0]] = fb["date"]
                except Exception:
                    pass

            # 1f. Hold durations (7-day window)
            seven_days_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                SELECT wallet_address, entry_timestamp,
                       COALESCE(last_sell_timestamp, exit_detected_at) as sell_time
                FROM mtew_token_positions
                WHERE still_holding = 0
                  AND entry_timestamp IS NOT NULL
                  AND COALESCE(last_sell_timestamp, exit_detected_at) IS NOT NULL
                  AND COALESCE(last_sell_timestamp, exit_detected_at) >= ?
            """, (seven_days_ago,))
            wallet_hold_durations: Dict[str, List[float]] = {}
            for r in cursor.fetchall():
                addr = r[0]
                try:
                    entry_str, exit_str = str(r[1]), str(r[2])
                    entry_dt = (datetime.fromisoformat(entry_str.replace("Z", "+00:00"))
                                if "T" in entry_str
                                else datetime.strptime(entry_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc))
                    exit_dt = (datetime.fromisoformat(exit_str.replace("Z", "+00:00"))
                               if "T" in exit_str
                               else datetime.strptime(exit_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc))
                    duration_h = (exit_dt - entry_dt).total_seconds() / 3600
                    if duration_h > 0.016:  # Skip sub-minute artifacts
                        if addr not in wallet_hold_durations:
                            wallet_hold_durations[addr] = []
                        wallet_hold_durations[addr].append(duration_h)
                except Exception:
                    pass

            # ============================================================
            # Phase 2: Aggregate per wallet (same logic as old endpoint)
            # ============================================================

            wallet_data: Dict[str, Dict[str, Any]] = {}

            for r in all_rows:
                addr = r[0]
                if addr not in wallet_data:
                    wallet_data[addr] = {
                        "tokens_traded": 0, "tokens_won": 0, "tokens_lost": 0,
                        "total_pnl": 0, "realized_pnl": 0, "unrealized_pnl": 0,
                        "pnl_1d": 0, "pnl_7d": 0, "pnl_30d": 0,
                        "best_pnl": 0, "best_token": None,
                        "worst_pnl": 0, "worst_token": None,
                        "wallet_balance_usd": None,
                        "entry_seconds_list": [],
                    }
                w = wallet_data[addr]
                w["tokens_traded"] += 1

                # Balance (max across tokens)
                bal = r[3]
                if bal is not None and (w["wallet_balance_usd"] is None or bal > w["wallet_balance_usd"]):
                    w["wallet_balance_usd"] = bal

                # Entry timing
                entry_sec = r[4]
                if entry_sec is not None:
                    w["entry_seconds_list"].append(entry_sec)

                verdict = r[9]
                token_name = r[8] or "?"

                # PnL from real data only
                pnl_key = (addr, r[1])
                if pnl_key in pnl_rows and pnl_rows[pnl_key]["source"] == "helius_enhanced":
                    p = pnl_rows[pnl_key]
                    token_pnl = p["pnl"] or 0
                    token_realized = p["realized"] or 0
                    token_unrealized = p["unrealized"] or 0
                else:
                    token_pnl = 0
                    token_realized = 0
                    token_unrealized = 0

                if verdict == "verified-win":
                    w["tokens_won"] += 1
                elif verdict == "verified-loss":
                    w["tokens_lost"] += 1

                w["total_pnl"] += token_pnl
                w["realized_pnl"] += token_realized
                w["unrealized_pnl"] += token_unrealized

                # Time-windowed PnL
                try:
                    ts = str(r[7] or "")
                    if "T" in ts:
                        token_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    else:
                        token_time = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    age = now - token_time
                    if age <= timedelta(days=1):
                        w["pnl_1d"] += token_pnl
                    if age <= timedelta(days=7):
                        w["pnl_7d"] += token_pnl
                    if age <= timedelta(days=30):
                        w["pnl_30d"] += token_pnl
                except Exception:
                    w["pnl_30d"] += token_pnl

                # Best/worst trade
                if token_pnl > w["best_pnl"]:
                    w["best_pnl"] = token_pnl
                    w["best_token"] = token_name
                if token_pnl < w["worst_pnl"]:
                    w["worst_pnl"] = token_pnl
                    w["worst_token"] = token_name

            # ============================================================
            # Phase 3: Write to cache tables (single transaction)
            # ============================================================

            cursor.execute("DELETE FROM wallet_leaderboard_cache")
            cursor.execute("DELETE FROM wallet_leaderboard_tags")
            cursor.execute("DELETE FROM wallet_leaderboard_tiers")

            cache_rows = []
            tag_rows = []
            tier_rows = []

            for addr, w in wallet_data.items():
                if w["tokens_traded"] < 2:
                    continue

                tt = w["tokens_traded"]
                entry_list = w["entry_seconds_list"]
                avg_entry = round(sum(entry_list) / len(entry_list), 1) if entry_list else None
                tiers = wallet_tiers.get(addr, {})
                tier_score = sum(TIER_SCORE_WEIGHTS.get(k, 0) * v for k, v in tiers.items())
                home_runs = sum(tiers.get(t, 0) for t in HOME_RUN_TIERS)
                rugs = sum(tiers.get(t, 0) for t in RUG_TIERS)

                hold_list = wallet_hold_durations.get(addr)
                avg_hold = round(sum(hold_list) / len(hold_list), 1) if hold_list else None

                cache_rows.append((
                    addr,
                    round(w["total_pnl"], 2), round(w["realized_pnl"], 2), round(w["unrealized_pnl"], 2),
                    round(w["pnl_1d"], 2), round(w["pnl_7d"], 2), round(w["pnl_30d"], 2),
                    tt, w["tokens_won"], w["tokens_lost"],
                    round(w["tokens_won"] / tt, 2) if tt > 0 else 0,
                    round(w["best_pnl"], 2), w["best_token"],
                    round(w["worst_pnl"], 2), w["worst_token"],
                    round(w["wallet_balance_usd"], 2) if w["wallet_balance_usd"] is not None else None,
                    avg_entry,
                    wallet_created_map.get(addr),
                    avg_hold,
                    tier_score, home_runs, rugs,
                    json.dumps(tiers), json.dumps(wallet_tags_map.get(addr, [])),
                ))

                # Tag rows
                for tag in wallet_tags_map.get(addr, []):
                    tag_rows.append((addr, tag.strip()))

                # Tier rows
                for tier_tag, cnt in tiers.items():
                    if cnt > 0:
                        tier_rows.append((addr, tier_tag, cnt))

            cursor.executemany("""
                INSERT INTO wallet_leaderboard_cache (
                    wallet_address, total_pnl_usd, realized_pnl_usd, unrealized_pnl_usd,
                    pnl_1d_usd, pnl_7d_usd, pnl_30d_usd,
                    tokens_traded, tokens_won, tokens_lost, win_rate,
                    best_trade_pnl, best_trade_token, worst_trade_pnl, worst_trade_token,
                    wallet_balance_usd, avg_entry_seconds, wallet_created_at, avg_hold_hours_7d,
                    tier_score, home_runs, rugs, tiers_json, tags_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, cache_rows)

            cursor.executemany(
                "INSERT OR IGNORE INTO wallet_leaderboard_tags (wallet_address, tag) VALUES (?, ?)",
                tag_rows,
            )

            cursor.executemany(
                "INSERT OR IGNORE INTO wallet_leaderboard_tiers (wallet_address, tier_tag, cnt) VALUES (?, ?, ?)",
                tier_rows,
            )

            result["wallets_cached"] = len(cache_rows)

    except Exception as e:
        log_error(f"[LeaderboardCache] Rebuild failed: {e}")
        result["error"] = str(e)
    finally:
        _last_rebuild_at = time.time()
        _rebuild_lock.release()

    elapsed = int((time.time() - t0) * 1000)
    result["duration_ms"] = elapsed
    log_info(f"[LeaderboardCache] Rebuilt: {result['wallets_cached']} wallets in {elapsed}ms")
    return result
