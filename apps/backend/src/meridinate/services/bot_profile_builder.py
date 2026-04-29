"""
Bot Profile Builder — Strategy Fingerprinting

Computes comprehensive strategy profiles from bot_probe transaction and
round-trip data. Produces both overall_strategy_profile and
meridinate_overlap_profile.

All computation is local (zero Helius credits).
"""

import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_info

CHICAGO_TZ = ZoneInfo("America/Chicago")


def build_profile(wallet_address: str, probe_run_id: int = None) -> Dict[str, Any]:
    """
    Build a complete strategy profile from probe data.

    Returns {
        overall_strategy_profile: {...},
        meridinate_overlap_profile: {...},
        behavioral_profile: {...},
        metadata: {...},
    }
    """
    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row

        # Load round trips
        query = "SELECT * FROM bot_probe_round_trips WHERE wallet_address = ?"
        params = [wallet_address]
        if probe_run_id:
            query += " AND probe_run_id = ?"
            params.append(probe_run_id)
        query += " ORDER BY entry_timestamp_unix"

        round_trips = [dict(r) for r in conn.execute(query, params).fetchall()]

        # Load token aggregates
        query2 = "SELECT * FROM bot_probe_token_aggregates WHERE wallet_address = ?"
        params2 = [wallet_address]
        if probe_run_id:
            query2 += " AND probe_run_id = ?"
            params2.append(probe_run_id)

        token_aggs = [dict(r) for r in conn.execute(query2, params2).fetchall()]

        # Load raw transactions for behavioral analysis
        query3 = "SELECT * FROM bot_probe_transactions WHERE wallet_address = ?"
        params3 = [wallet_address]
        if probe_run_id:
            query3 += " AND probe_run_id = ?"
            params3.append(probe_run_id)
        query3 += " ORDER BY timestamp_unix"

        raw_txs = [dict(r) for r in conn.execute(query3, params3).fetchall()]

        # Load Meridinate token data for overlap analysis
        token_addrs = list({ta["token_address"] for ta in token_aggs})
        meridinate_tokens = {}
        if token_addrs:
            placeholders = ",".join("?" for _ in token_addrs)
            rows = conn.execute(f"""
                SELECT at.token_address, at.token_name, at.score_composite, at.market_cap_ath,
                       at.market_cap_usd, at.market_cap_usd_current, at.fresh_wallet_pct,
                       at.controlled_supply_score, at.bundle_cluster_count,
                       tt_win.tag as win_tag, tt_loss.tag as loss_tag
                FROM analyzed_tokens at
                LEFT JOIN token_tags tt_win ON tt_win.token_id = at.id AND tt_win.tag = 'verified-win'
                LEFT JOIN token_tags tt_loss ON tt_loss.token_id = at.id AND tt_loss.tag = 'verified-loss'
                WHERE at.token_address IN ({placeholders})
            """, token_addrs).fetchall()
            for r in rows:
                meridinate_tokens[r["token_address"]] = dict(r)

    if not round_trips and not token_aggs:
        return {"error": "No probe data found", "wallet_address": wallet_address}

    # ================================================================
    # PERFORMANCE PROFILE
    # ================================================================
    winning_trips = [rt for rt in round_trips if (rt.get("pnl_sol") or 0) > 0]
    losing_trips = [rt for rt in round_trips if (rt.get("pnl_sol") or 0) <= 0]

    total_won_sol = sum(rt["pnl_sol"] for rt in winning_trips)
    total_lost_sol = sum(abs(rt["pnl_sol"]) for rt in losing_trips)

    win_rate = len(winning_trips) / max(len(round_trips), 1)
    avg_win = total_won_sol / max(len(winning_trips), 1)
    avg_loss = total_lost_sol / max(len(losing_trips), 1)
    expectancy = avg_win * win_rate - avg_loss * (1 - win_rate) if round_trips else 0
    profit_factor = total_won_sol / max(total_lost_sol, 0.001) if total_lost_sol > 0 else float('inf')

    # Token-level win rate
    token_wins = sum(1 for ta in token_aggs if (ta.get("realized_pnl_sol") or 0) > 0)
    token_losses = sum(1 for ta in token_aggs if (ta.get("realized_pnl_sol") or 0) <= 0 and ta.get("sell_count", 0) > 0)

    # Daily PnL
    daily_pnl = defaultdict(lambda: {"pnl_sol": 0, "trades": 0, "wins": 0})
    for rt in round_trips:
        if rt.get("exit_timestamp"):
            try:
                dt = datetime.fromisoformat(str(rt["exit_timestamp"]).replace("Z", "+00:00"))
                day = dt.strftime("%Y-%m-%d")
                daily_pnl[day]["pnl_sol"] += rt.get("pnl_sol", 0)
                daily_pnl[day]["trades"] += 1
                if (rt.get("pnl_sol") or 0) > 0:
                    daily_pnl[day]["wins"] += 1
            except (ValueError, TypeError):
                pass

    daily_series = [{"date": d, **v} for d, v in sorted(daily_pnl.items())]
    profitable_days = sum(1 for d in daily_series if d["pnl_sol"] > 0)
    daily_consistency = profitable_days / max(len(daily_series), 1)

    performance = {
        "total_round_trips": len(round_trips),
        "total_tokens_traded": len(token_aggs),
        "win_rate_by_trade": round(win_rate, 4),
        "win_rate_by_token": round(token_wins / max(token_wins + token_losses, 1), 4),
        "total_realized_pnl_sol": round(sum(rt.get("pnl_sol", 0) for rt in round_trips), 6),
        "avg_pnl_per_trade_sol": round(expectancy, 6) if round_trips else 0,
        "avg_pnl_per_win_sol": round(avg_win, 6),
        "avg_pnl_per_loss_sol": round(-avg_loss, 6),
        "expectancy_per_trade_sol": round(expectancy, 6),
        "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else None,
        "best_trade_sol": round(max((rt.get("pnl_sol", 0) for rt in round_trips), default=0), 6),
        "worst_trade_sol": round(min((rt.get("pnl_sol", 0) for rt in round_trips), default=0), 6),
        "daily_pnl_consistency": round(daily_consistency, 3),
        "profitable_days": profitable_days,
        "total_days_traded": len(daily_series),
        "max_drawdown_day_sol": round(min((d["pnl_sol"] for d in daily_series), default=0), 6),
    }

    # ================================================================
    # ENTRY BEHAVIOR
    # ================================================================
    entry_seconds = [rt.get("entry_seconds_after_creation") for rt in round_trips
                     if rt.get("entry_seconds_after_creation") is not None]

    entry_timing_buckets = {"first_block_lt2s": 0, "lightning_2_10s": 0, "fast_10_60s": 0,
                            "early_1_5min": 0, "normal_5_30min": 0, "late_gt30min": 0}
    for s in entry_seconds:
        if s < 2: entry_timing_buckets["first_block_lt2s"] += 1
        elif s < 10: entry_timing_buckets["lightning_2_10s"] += 1
        elif s < 60: entry_timing_buckets["fast_10_60s"] += 1
        elif s < 300: entry_timing_buckets["early_1_5min"] += 1
        elif s < 1800: entry_timing_buckets["normal_5_30min"] += 1
        else: entry_timing_buckets["late_gt30min"] += 1

    total_entry = max(len(entry_seconds), 1)
    entry_dist = {k: round(v / total_entry, 3) for k, v in entry_timing_buckets.items()}

    # Time of day / day of week
    hour_dist = defaultdict(int)
    dow_dist = defaultdict(int)
    entries_by_date = defaultdict(int)
    for rt in round_trips:
        if rt.get("entry_timestamp"):
            try:
                dt = datetime.fromisoformat(str(rt["entry_timestamp"]).replace("Z", "+00:00"))
                hour_dist[dt.hour] += 1
                dow_dist[dt.strftime("%a")] += 1
                entries_by_date[dt.strftime("%Y-%m-%d")] += 1
            except (ValueError, TypeError):
                pass

    entry_profile = {
        "avg_entry_seconds": round(sum(entry_seconds) / max(len(entry_seconds), 1), 1) if entry_seconds else None,
        "median_entry_seconds": round(sorted(entry_seconds)[len(entry_seconds)//2], 1) if entry_seconds else None,
        "entry_timing_distribution": entry_dist,
        "entries_per_day_avg": round(len(round_trips) / max(len(entries_by_date), 1), 1),
        "time_of_day_distribution": dict(sorted(hour_dist.items())),
        "day_of_week_distribution": dict(dow_dist),
    }

    # ================================================================
    # EXIT BEHAVIOR
    # ================================================================
    winner_holds = [rt["hold_seconds"] for rt in winning_trips if rt.get("hold_seconds") is not None]
    loser_holds = [rt["hold_seconds"] for rt in losing_trips if rt.get("hold_seconds") is not None]
    all_holds = [rt["hold_seconds"] for rt in round_trips if rt.get("hold_seconds") is not None]

    hold_buckets = {"flash_lt30s": 0, "quick_30s_2min": 0, "short_2_10min": 0,
                    "medium_10min_1hr": 0, "long_gt1hr": 0}
    for h in all_holds:
        if h < 30: hold_buckets["flash_lt30s"] += 1
        elif h < 120: hold_buckets["quick_30s_2min"] += 1
        elif h < 600: hold_buckets["short_2_10min"] += 1
        elif h < 3600: hold_buckets["medium_10min_1hr"] += 1
        else: hold_buckets["long_gt1hr"] += 1

    total_holds = max(len(all_holds), 1)
    hold_dist = {k: round(v / total_holds, 3) for k, v in hold_buckets.items()}

    # Take-profit / stop-loss estimates from multiples
    win_multiples = [rt["pnl_multiple"] for rt in winning_trips if rt.get("pnl_multiple")]
    loss_multiples = [rt["pnl_multiple"] for rt in losing_trips if rt.get("pnl_multiple")]

    exit_profile = {
        "avg_hold_seconds_winners": round(sum(winner_holds) / max(len(winner_holds), 1), 1) if winner_holds else None,
        "avg_hold_seconds_losers": round(sum(loser_holds) / max(len(loser_holds), 1), 1) if loser_holds else None,
        "median_hold_seconds": round(sorted(all_holds)[len(all_holds)//2], 1) if all_holds else None,
        "hold_distribution": hold_dist,
        "avg_exit_multiple_winners": round(sum(win_multiples) / max(len(win_multiples), 1), 4) if win_multiples else None,
        "avg_exit_multiple_losers": round(sum(loss_multiples) / max(len(loss_multiples), 1), 4) if loss_multiples else None,
    }

    # ================================================================
    # POSITION SIZING
    # ================================================================
    entry_sizes = [rt.get("entry_sol", 0) for rt in round_trips if rt.get("entry_sol")]

    sizing_profile = {
        "avg_position_sol": round(sum(entry_sizes) / max(len(entry_sizes), 1), 6) if entry_sizes else None,
        "median_position_sol": round(sorted(entry_sizes)[len(entry_sizes)//2], 6) if entry_sizes else None,
        "min_position_sol": round(min(entry_sizes), 6) if entry_sizes else None,
        "max_position_sol": round(max(entry_sizes), 6) if entry_sizes else None,
        "stddev_position_sol": round(_stddev(entry_sizes), 6) if len(entry_sizes) > 1 else None,
    }

    # ================================================================
    # INFRASTRUCTURE
    # ================================================================
    tip_counts = defaultdict(int)
    for tx in raw_txs:
        tip = tx.get("tip_type")
        tip_counts[tip or "standard"] += 1

    total_txs = max(sum(tip_counts.values()), 1)
    infra_profile = {
        "nozomi_rate": round(tip_counts.get("nozomi", 0) / total_txs, 3),
        "jito_rate": round(tip_counts.get("jito", 0) / total_txs, 3),
        "standard_rate": round(tip_counts.get("standard", 0) / total_txs, 3),
        "uses_nozomi": tip_counts.get("nozomi", 0) > 0,
        "uses_jito": tip_counts.get("jito", 0) > 0,
        "primary_infrastructure": max(tip_counts, key=tip_counts.get) if tip_counts else "unknown",
    }

    # ================================================================
    # BEHAVIORAL PROFILE (multi-entry/exit patterns)
    # ================================================================
    tokens_by_addr = defaultdict(list)
    for tx in raw_txs:
        tokens_by_addr[tx["token_address"]].append(tx)

    multi_buy_tokens = 0
    multi_sell_tokens = 0
    reentry_tokens = 0
    add_to_winner_count = 0
    add_to_loser_count = 0
    add_total = 0

    for token_addr, txs in tokens_by_addr.items():
        buys = [t for t in txs if t["direction"] == "buy"]
        sells = [t for t in txs if t["direction"] == "sell"]

        if len(buys) > 1:
            multi_buy_tokens += 1
        if len(sells) > 1:
            multi_sell_tokens += 1

        # Check for re-entry: buy after a sell
        if sells and buys:
            last_sell_ts = max(t.get("timestamp_unix", 0) or 0 for t in sells)
            buys_after_sell = [b for b in buys if (b.get("timestamp_unix", 0) or 0) > last_sell_ts]
            if buys_after_sell:
                reentry_tokens += 1

        # Add-to-winner vs add-to-loser (using cost basis)
        for i, buy in enumerate(buys):
            if i == 0:
                continue  # First buy has no prior cost basis
            avg_cost_before = buy.get("position_avg_cost_before", 0)
            if avg_cost_before and avg_cost_before > 0:
                add_total += 1
                # Current "price" approximation: this buy's sol_per_token
                buy_price = buy.get("sol_amount", 0) / max(buy.get("token_amount", 1), 0.001)
                if buy_price > avg_cost_before:
                    add_to_winner_count += 1
                else:
                    add_to_loser_count += 1

    # Partial takes
    partial_trips = sum(1 for rt in round_trips if rt.get("trip_type") == "partial")

    total_tokens_with_trades = max(len(tokens_by_addr), 1)
    behavioral = {
        "avg_buys_per_token": round(sum(len([t for t in txs if t["direction"] == "buy"]) for txs in tokens_by_addr.values()) / total_tokens_with_trades, 2),
        "avg_sells_per_token": round(sum(len([t for t in txs if t["direction"] == "sell"]) for txs in tokens_by_addr.values()) / total_tokens_with_trades, 2),
        "avg_round_trips_per_token": round(len(round_trips) / total_tokens_with_trades, 2),
        "multi_buy_rate": round(multi_buy_tokens / total_tokens_with_trades, 3),
        "multi_sell_rate": round(multi_sell_tokens / total_tokens_with_trades, 3),
        "partial_take_rate": round(partial_trips / max(len(round_trips), 1), 3),
        "reentry_after_exit_rate": round(reentry_tokens / total_tokens_with_trades, 3),
        "add_to_winner_rate": round(add_to_winner_count / max(add_total, 1), 3),
        "add_to_loser_rate": round(add_to_loser_count / max(add_total, 1), 3),
        "add_events_total": add_total,
    }

    # ================================================================
    # MERIDINATE OVERLAP PROFILE
    # ================================================================
    overlap_wins = 0
    overlap_losses = 0
    overlap_scores = []
    overlap_details = []

    for ta in token_aggs:
        mt = meridinate_tokens.get(ta["token_address"])
        if not mt:
            continue
        pnl = ta.get("realized_pnl_sol", 0) or 0
        is_win = pnl > 0 and ta.get("sell_count", 0) > 0
        if is_win:
            overlap_wins += 1
        elif ta.get("sell_count", 0) > 0:
            overlap_losses += 1

        if mt.get("score_composite"):
            overlap_scores.append(mt["score_composite"])

        token_verdict = "win" if mt.get("win_tag") else ("loss" if mt.get("loss_tag") else "pending")
        overlap_details.append({
            "token_address": ta["token_address"],
            "token_name": ta.get("token_name"),
            "bot_pnl_sol": round(pnl, 6),
            "bot_won": is_win,
            "meridinate_verdict": token_verdict,
            "meridinate_score": mt.get("score_composite"),
            "fresh_wallet_pct": mt.get("fresh_wallet_pct"),
            "controlled_supply": mt.get("controlled_supply_score"),
        })

    meridinate_overlap = {
        "tokens_in_meridinate": len(meridinate_tokens),
        "tokens_probed": len(token_aggs),
        "overlap_count": len(overlap_details),
        "bot_win_rate_on_overlap": round(overlap_wins / max(overlap_wins + overlap_losses, 1), 4),
        "avg_meridinate_score": round(sum(overlap_scores) / max(len(overlap_scores), 1), 1) if overlap_scores else None,
        "details": overlap_details[:50],  # Cap for storage
    }

    # ================================================================
    # STRATEGY ARCHETYPE CLASSIFICATION (heuristic)
    # ================================================================
    archetype = "unclear"
    if performance["total_round_trips"] < 5:
        archetype = "insufficient_data"
    elif entry_profile.get("median_entry_seconds") is not None and entry_profile["median_entry_seconds"] < 10:
        archetype = "speed_sniper"
    elif entry_profile.get("median_entry_seconds") is not None and entry_profile["median_entry_seconds"] < 60:
        if behavioral["avg_round_trips_per_token"] > 2:
            archetype = "momentum_manager"
        else:
            archetype = "speed_sniper"
    elif performance["win_rate_by_trade"] > 0.55 and len(token_aggs) < 50:
        archetype = "selective_value"
    elif len(token_aggs) > 100 and performance["win_rate_by_trade"] < 0.3:
        archetype = "spray_and_pray"
    elif behavioral["multi_buy_rate"] > 0.4 and behavioral["add_to_loser_rate"] > 0.5:
        archetype = "averaging_down_bot"
    elif performance["daily_pnl_consistency"] > 0.85:
        archetype = "consistent_operator"

    # ================================================================
    # ASSEMBLE
    # ================================================================
    profile = {
        "wallet_address": wallet_address,
        "archetype": archetype,
        "round_trip_accounting_method": "FIFO",
        "performance": performance,
        "entry_behavior": entry_profile,
        "exit_behavior": exit_profile,
        "position_sizing": sizing_profile,
        "infrastructure": infra_profile,
        "behavioral": behavioral,
        "meridinate_overlap": meridinate_overlap,
        "daily_pnl_series": daily_series[-30:],  # Last 30 days
    }

    # Store profile
    with db.get_db_connection() as conn:
        conn.execute("DELETE FROM bot_probe_profiles WHERE wallet_address = ?", (wallet_address,))
        conn.execute("""
            INSERT INTO bot_probe_profiles
            (wallet_address, profile_json, total_trades, win_rate, expectancy_sol,
             avg_hold_seconds, infrastructure, computed_at, credits_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            wallet_address,
            json.dumps(profile, default=str),
            performance["total_round_trips"],
            performance["win_rate_by_trade"],
            performance["expectancy_per_trade_sol"],
            exit_profile.get("median_hold_seconds"),
            infra_profile["primary_infrastructure"],
            datetime.now(CHICAGO_TZ).strftime("%Y-%m-%d %H:%M:%S %Z"),
        ))

    log_info(f"[BotProfile] Built profile for {wallet_address[:16]}...: "
             f"{archetype}, {performance['total_round_trips']} trips, "
             f"{performance['win_rate_by_trade']:.0%} WR, "
             f"{performance['expectancy_per_trade_sol']:.4f} SOL/trade")

    return profile


def compare_profiles(wallet_a: str, wallet_b: str) -> Dict[str, Any]:
    """Phase 4: Compare two bot profiles side-by-side."""
    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        row_a = conn.execute("SELECT profile_json FROM bot_probe_profiles WHERE wallet_address = ?", (wallet_a,)).fetchone()
        row_b = conn.execute("SELECT profile_json FROM bot_probe_profiles WHERE wallet_address = ?", (wallet_b,)).fetchone()

    if not row_a or not row_b:
        return {"error": "One or both profiles not found"}

    profile_a = json.loads(row_a["profile_json"])
    profile_b = json.loads(row_b["profile_json"])

    pa = profile_a["performance"]
    pb = profile_b["performance"]
    ea = profile_a["entry_behavior"]
    eb = profile_b["entry_behavior"]
    xa = profile_a["exit_behavior"]
    xb = profile_b["exit_behavior"]
    ba = profile_a["behavioral"]
    bb = profile_b["behavioral"]

    comparison = {
        "wallet_a": wallet_a,
        "wallet_b": wallet_b,
        "archetype_a": profile_a["archetype"],
        "archetype_b": profile_b["archetype"],
        "speed": {
            "a_median_entry_seconds": ea.get("median_entry_seconds"),
            "b_median_entry_seconds": eb.get("median_entry_seconds"),
            "faster": "a" if (ea.get("median_entry_seconds") or 999) < (eb.get("median_entry_seconds") or 999) else "b",
        },
        "selectivity": {
            "a_tokens_traded": pa["total_tokens_traded"],
            "b_tokens_traded": pb["total_tokens_traded"],
            "a_entries_per_day": ea.get("entries_per_day_avg"),
            "b_entries_per_day": eb.get("entries_per_day_avg"),
            "more_selective": "a" if pa["total_tokens_traded"] < pb["total_tokens_traded"] else "b",
        },
        "win_rate": {
            "a_by_trade": pa["win_rate_by_trade"],
            "b_by_trade": pb["win_rate_by_trade"],
            "a_by_token": pa["win_rate_by_token"],
            "b_by_token": pb["win_rate_by_token"],
            "higher_trade_wr": "a" if pa["win_rate_by_trade"] > pb["win_rate_by_trade"] else "b",
        },
        "expectancy": {
            "a_per_trade_sol": pa["expectancy_per_trade_sol"],
            "b_per_trade_sol": pb["expectancy_per_trade_sol"],
            "a_profit_factor": pa["profit_factor"],
            "b_profit_factor": pb["profit_factor"],
            "higher_expectancy": "a" if pa["expectancy_per_trade_sol"] > pb["expectancy_per_trade_sol"] else "b",
        },
        "hold_time": {
            "a_median_seconds": xa.get("median_hold_seconds"),
            "b_median_seconds": xb.get("median_hold_seconds"),
            "a_winners_avg": xa.get("avg_hold_seconds_winners"),
            "b_winners_avg": xb.get("avg_hold_seconds_winners"),
            "a_losers_avg": xa.get("avg_hold_seconds_losers"),
            "b_losers_avg": xb.get("avg_hold_seconds_losers"),
            "cuts_losses_faster": "a" if (xa.get("avg_hold_seconds_losers") or 999) < (xb.get("avg_hold_seconds_losers") or 999) else "b",
        },
        "sizing": {
            "a_avg_sol": profile_a["position_sizing"].get("avg_position_sol"),
            "b_avg_sol": profile_b["position_sizing"].get("avg_position_sol"),
        },
        "behavior": {
            "a_add_to_winner_rate": ba["add_to_winner_rate"],
            "b_add_to_winner_rate": bb["add_to_winner_rate"],
            "a_partial_take_rate": ba["partial_take_rate"],
            "b_partial_take_rate": bb["partial_take_rate"],
            "a_reentry_rate": ba["reentry_after_exit_rate"],
            "b_reentry_rate": bb["reentry_after_exit_rate"],
        },
        "consistency": {
            "a_daily_consistency": pa["daily_pnl_consistency"],
            "b_daily_consistency": pb["daily_pnl_consistency"],
            "more_consistent": "a" if pa["daily_pnl_consistency"] > pb["daily_pnl_consistency"] else "b",
        },
        "infrastructure": {
            "a": profile_a["infrastructure"],
            "b": profile_b["infrastructure"],
        },
    }

    # Find token overlap
    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT a.token_address, a.token_name,
                   a.realized_pnl_sol as a_pnl, b.realized_pnl_sol as b_pnl,
                   a.buy_count as a_buys, b.buy_count as b_buys,
                   a.entry_seconds_after_creation as a_entry, b.entry_seconds_after_creation as b_entry
            FROM bot_probe_token_aggregates a
            JOIN bot_probe_token_aggregates b ON a.token_address = b.token_address
            WHERE a.wallet_address = ? AND b.wallet_address = ?
            ORDER BY a.realized_pnl_sol DESC
        """, (wallet_a, wallet_b)).fetchall()

    overlap = [dict(r) for r in rows]
    comparison["token_overlap"] = {
        "count": len(overlap),
        "tokens": overlap[:20],
        "a_won_b_lost": sum(1 for o in overlap if (o.get("a_pnl") or 0) > 0 and (o.get("b_pnl") or 0) <= 0),
        "b_won_a_lost": sum(1 for o in overlap if (o.get("b_pnl") or 0) > 0 and (o.get("a_pnl") or 0) <= 0),
        "both_won": sum(1 for o in overlap if (o.get("a_pnl") or 0) > 0 and (o.get("b_pnl") or 0) > 0),
        "both_lost": sum(1 for o in overlap if (o.get("a_pnl") or 0) <= 0 and (o.get("b_pnl") or 0) <= 0),
    }

    # Store comparison
    with db.get_db_connection() as conn:
        conn.execute("UPDATE bot_probe_profiles SET comparison_json = ? WHERE wallet_address = ?",
                     (json.dumps(comparison, default=str), wallet_a))
        conn.execute("UPDATE bot_probe_profiles SET comparison_json = ? WHERE wallet_address = ?",
                     (json.dumps(comparison, default=str), wallet_b))

    log_info(f"[BotProfile] Comparison: {wallet_a[:12]}... vs {wallet_b[:12]}... — "
             f"{len(overlap)} overlapping tokens")

    return comparison


def _stddev(values: List[float]) -> float:
    if len(values) < 2:
        return 0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)
