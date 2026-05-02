"""
Intel Pre-Computation Layer

Generates a database snapshot and investigation leads for the Intel Agents.
Pure DB queries, zero external API calls, runs in <2 seconds.
"""

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_info


def generate_snapshot_and_leads() -> Dict[str, Any]:
    """
    Generate a comprehensive database snapshot and investigation leads.

    Returns:
        {
            snapshot: str (human-readable summary),
            leads: str (investigation leads for the agent),
            raw: dict (structured data for programmatic use),
        }
    """
    now = datetime.now(timezone.utc)
    raw: Dict[str, Any] = {}

    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # ================================================================
        # DATABASE OVERVIEW
        # ================================================================
        cursor.execute("SELECT COUNT(*) FROM analyzed_tokens WHERE deleted_at IS NULL OR deleted_at = ''")
        total_tokens = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM analyzed_tokens WHERE (deleted_at IS NULL OR deleted_at = '') AND score_composite IS NOT NULL")
        scored_tokens = cursor.fetchone()[0]

        cursor.execute("""
            SELECT
                SUM(CASE WHEN tt.tag = 'verified-win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN tt.tag = 'verified-loss' THEN 1 ELSE 0 END) as losses
            FROM token_tags tt
            WHERE tt.tag IN ('verified-win', 'verified-loss')
        """)
        r = cursor.fetchone()
        total_wins = r[0] or 0
        total_losses = r[1] or 0
        pending = total_tokens - total_wins - total_losses

        cursor.execute("SELECT COUNT(DISTINCT wallet_address) FROM wallet_leaderboard_cache")
        total_wallets = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM starred_items WHERE item_type = 'wallet'")
        starred_wallets = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM starred_items WHERE item_type = 'token'")
        starred_tokens = cursor.fetchone()[0]

        cursor.execute("SELECT MAX(analysis_timestamp) FROM analyzed_tokens WHERE deleted_at IS NULL OR deleted_at = ''")
        latest_scan = cursor.fetchone()[0]

        raw["overview"] = {
            "total_tokens": total_tokens, "wins": total_wins, "losses": total_losses,
            "pending": pending, "total_wallets": total_wallets,
            "starred_wallets": starred_wallets, "starred_tokens": starred_tokens,
        }

        # ================================================================
        # TOP PERFORMERS (wallets)
        # ================================================================
        cursor.execute("""
            SELECT wallet_address, total_pnl_usd, realized_pnl_usd, tokens_traded,
                   win_rate, home_runs, rugs, tier_score, tags_json
            FROM wallet_leaderboard_cache
            ORDER BY total_pnl_usd DESC
            LIMIT 20
        """)
        top_wallets = [dict(r) for r in cursor.fetchall()]
        raw["top_wallets"] = top_wallets

        # ================================================================
        # PNL BACKFILL for top wallets with insufficient real data
        # ================================================================
        # Top wallets often appear on only 2-3 of our tokens. Backfill their
        # PnL data so the behavior profiler has enough to classify them.
        wallets_needing_backfill = []
        for tw in top_wallets:
            addr = tw["wallet_address"]
            cursor.execute("""
                SELECT COUNT(*) FROM mtew_token_positions
                WHERE wallet_address = ? AND pnl_source = 'helius_enhanced'
            """, (addr,))
            real_count = cursor.fetchone()[0]
            tokens_traded = tw.get("tokens_traded", 0)
            if real_count < 5 and tokens_traded >= 3:
                wallets_needing_backfill.append(addr)

        if wallets_needing_backfill:
            try:
                from meridinate.services.pnl_calculator_v2 import compute_and_store_wallet_pnl_v2
                from meridinate.settings import HELIUS_API_KEY
                backfill_credits = 0
                for addr in wallets_needing_backfill[:10]:  # Cap at 10 wallets per run
                    try:
                        pnl_result = compute_and_store_wallet_pnl_v2(addr, HELIUS_API_KEY)
                        backfill_credits += pnl_result.get("credits_used", 0)
                    except Exception as e:
                        log_error(f"[IntelPrecompute] PnL backfill failed for {addr[:12]}: {e}")
                if backfill_credits > 0:
                    log_info(f"[IntelPrecompute] Backfilled PnL for {len(wallets_needing_backfill)} wallets ({backfill_credits} credits)")
                raw["pnl_backfill"] = {
                    "wallets_backfilled": len(wallets_needing_backfill),
                    "credits_used": backfill_credits,
                }
            except Exception as e:
                log_error(f"[IntelPrecompute] PnL backfill step failed: {e}")

        # ================================================================
        # BOT BEHAVIOR PROFILES (computed from trade-level position data)
        # ================================================================
        # For wallets with real PnL data, compute trading behavior
        # to classify bot strategy: Sniper, Copy Bot, Scalper, Accumulator, Runner, Spray Bot
        top_wallet_addrs = [w["wallet_address"] for w in top_wallets]
        if top_wallet_addrs:
            placeholders = ",".join("?" * len(top_wallet_addrs))
            cursor.execute(f"""
                SELECT
                    mtp.wallet_address,
                    COUNT(DISTINCT mtp.token_id) as tokens_traded,
                    AVG(CASE WHEN mtp.pnl_source = 'helius_enhanced' AND mtp.total_sold_usd > 0 AND mtp.total_bought_usd > 0
                        THEN mtp.total_sold_usd / mtp.total_bought_usd END) as avg_return_ratio,
                    AVG(CASE WHEN mtp.pnl_source = 'helius_enhanced' AND mtp.realized_pnl > 0
                        THEN mtp.total_sold_usd / NULLIF(mtp.total_bought_usd, 0) END) as avg_win_multiple,
                    AVG(CASE WHEN mtp.pnl_source = 'helius_enhanced' AND mtp.realized_pnl < 0 AND mtp.still_holding = 0
                        THEN mtp.total_sold_usd / NULLIF(mtp.total_bought_usd, 0) END) as avg_loss_ratio,
                    AVG(mtp.buy_count) as avg_buys_per_token,
                    AVG(mtp.sell_count) as avg_sells_per_token,
                    AVG(CASE WHEN mtp.still_holding = 0 AND mtp.entry_timestamp IS NOT NULL
                            AND COALESCE(mtp.last_sell_timestamp, mtp.exit_detected_at) IS NOT NULL
                        THEN (julianday(COALESCE(mtp.last_sell_timestamp, mtp.exit_detected_at)) - julianday(mtp.entry_timestamp)) * 24 * 60
                        END) as avg_hold_minutes,
                    SUM(CASE WHEN mtp.pnl_source = 'helius_enhanced' AND mtp.realized_pnl > 0 THEN 1 ELSE 0 END) as win_count,
                    SUM(CASE WHEN mtp.pnl_source = 'helius_enhanced' AND mtp.realized_pnl <= 0 AND mtp.still_holding = 0 THEN 1 ELSE 0 END) as loss_count,
                    AVG(mtp.total_bought_usd) as avg_position_size,
                    SUM(mtp.total_bought_usd) as total_volume
                FROM mtew_token_positions mtp
                WHERE mtp.wallet_address IN ({placeholders})
                AND mtp.pnl_source = 'helius_enhanced'
                GROUP BY mtp.wallet_address
                HAVING tokens_traded >= 3
            """, top_wallet_addrs)
            behavior_rows = [dict(r) for r in cursor.fetchall()]

            # Also get entry timing from early_buyer_wallets
            cursor.execute(f"""
                SELECT wallet_address, AVG(avg_entry_seconds) as avg_entry_seconds,
                       COUNT(CASE WHEN avg_entry_seconds < 5 THEN 1 END) as block0_entries,
                       COUNT(CASE WHEN avg_entry_seconds < 30 THEN 1 END) as fast_entries,
                       COUNT(*) as total_entries
                FROM early_buyer_wallets
                WHERE wallet_address IN ({placeholders})
                AND avg_entry_seconds IS NOT NULL
                GROUP BY wallet_address
            """, top_wallet_addrs)
            entry_map = {r[0]: dict(zip(["wallet_address", "avg_entry_seconds", "block0_entries", "fast_entries", "total_entries"], r)) for r in cursor.fetchall()}

            # Also get infrastructure tags
            cursor.execute(f"""
                SELECT wallet_address, GROUP_CONCAT(tag) as tags
                FROM wallet_tags
                WHERE wallet_address IN ({placeholders})
                AND tag IN ('Sniper Bot', 'Automated (Nozomi)', 'Bundled (Jito)', 'Lightning Buyer')
                GROUP BY wallet_address
            """, top_wallet_addrs)
            infra_map = {r[0]: r[1] for r in cursor.fetchall()}

            # Classify each wallet's bot strategy
            bot_profiles = []
            for bw in behavior_rows:
                addr = bw["wallet_address"]
                entry = entry_map.get(addr, {})
                infra_tags = infra_map.get(addr, "")

                avg_entry = entry.get("avg_entry_seconds")
                block0_pct = (entry.get("block0_entries", 0) / entry.get("total_entries", 1) * 100) if entry.get("total_entries") else 0
                fast_pct = (entry.get("fast_entries", 0) / entry.get("total_entries", 1) * 100) if entry.get("total_entries") else 0
                avg_hold = bw.get("avg_hold_minutes")
                avg_buys = bw.get("avg_buys_per_token") or 1
                avg_win_mult = bw.get("avg_win_multiple")
                avg_loss_ratio = bw.get("avg_loss_ratio")
                tokens = bw.get("tokens_traded", 0)
                wins = bw.get("win_count", 0)
                losses = bw.get("loss_count", 0)
                win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0

                # Strategy classification — confident tier first, small-sample fallback after.
                # Confident tier requires enough tokens to be statistically meaningful.
                strategy = "Unknown"
                confidence = "low"
                if block0_pct > 50:
                    strategy, confidence = "Sniper", "high"
                elif avg_buys > 2.5:
                    strategy, confidence = "Accumulator", "high"
                elif avg_win_mult and avg_win_mult > 8:
                    strategy, confidence = "Runner", "high"
                elif avg_hold and avg_hold < 30 and tokens > 15:
                    strategy, confidence = "Scalper", "high"
                elif tokens > 30 and win_rate < 35:
                    strategy, confidence = "Spray Bot", "high"
                elif fast_pct > 60 and win_rate > 40:
                    strategy, confidence = "Sniper", "medium"
                elif tokens > 10 and win_rate > 40:
                    strategy, confidence = "Scalper", "medium"
                else:
                    # Small-sample tentative tier (3 <= tokens <= 10).
                    # Lean on win-rate + entry timing + hold time so the Investigator
                    # gets a hint instead of "Unknown" and a re-investigation.
                    if tokens >= 3:
                        if avg_hold and avg_hold < 30 and win_rate >= 50:
                            strategy, confidence = "Scalper", "tentative"
                        elif avg_win_mult and avg_win_mult >= 5:
                            strategy, confidence = "Runner", "tentative"
                        elif fast_pct >= 50:
                            strategy, confidence = "Sniper", "tentative"
                        elif win_rate <= 30:
                            strategy, confidence = "Spray Bot", "tentative"
                        elif win_rate >= 50:
                            strategy, confidence = "Scalper", "tentative"

                profile = {
                    "wallet_address": addr,
                    "strategy": strategy,
                    "strategy_confidence": confidence,
                    "tokens_traded": tokens,
                    "win_rate": round(win_rate, 1),
                    "avg_entry_seconds": round(avg_entry, 1) if avg_entry else None,
                    "block0_entry_pct": round(block0_pct, 1),
                    "avg_hold_minutes": round(avg_hold, 1) if avg_hold else None,
                    "avg_buys_per_token": round(avg_buys, 1),
                    "avg_win_multiple": round(avg_win_mult, 2) if avg_win_mult else None,
                    "avg_loss_cut": round(avg_loss_ratio, 2) if avg_loss_ratio else None,
                    "avg_position_size_usd": round(bw.get("avg_position_size") or 0, 2),
                    "infra_tags": infra_tags,
                }
                bot_profiles.append(profile)

            raw["bot_profiles"] = bot_profiles
        else:
            raw["bot_profiles"] = []

        # ================================================================
        # RECENTLY ACTIVE WALLETS (appeared in tokens scanned in last 48h)
        # ================================================================
        two_days_ago = (now - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            SELECT DISTINCT ebw.wallet_address, wlc.total_pnl_usd, wlc.win_rate, wlc.home_runs, wlc.tags_json
            FROM early_buyer_wallets ebw
            JOIN analyzed_tokens t ON t.id = ebw.token_id
            JOIN wallet_leaderboard_cache wlc ON wlc.wallet_address = ebw.wallet_address
            WHERE t.analysis_timestamp >= ? AND (t.deleted_at IS NULL OR t.deleted_at = '')
            AND wlc.total_pnl_usd > 1000
            ORDER BY wlc.total_pnl_usd DESC
            LIMIT 30
        """, (two_days_ago,))
        recently_active_profitable = [dict(r) for r in cursor.fetchall()]
        raw["recently_active_profitable"] = recently_active_profitable

        # ================================================================
        # CONVERGENCE: Tokens where 3+ Consistent Winners bought
        # ================================================================
        cursor.execute("""
            SELECT t.id, t.token_name, t.token_address, t.analysis_timestamp,
                   t.market_cap_usd_current, t.score_composite,
                   COUNT(DISTINCT ebw.wallet_address) as winner_count,
                   GROUP_CONCAT(DISTINCT ebw.wallet_address) as winner_wallets
            FROM analyzed_tokens t
            JOIN early_buyer_wallets ebw ON ebw.token_id = t.id
            JOIN wallet_tags wt ON wt.wallet_address = ebw.wallet_address AND wt.tag = 'Consistent Winner'
            WHERE t.analysis_timestamp >= ?
            AND (t.deleted_at IS NULL OR t.deleted_at = '')
            GROUP BY t.id
            HAVING winner_count >= 3
            ORDER BY winner_count DESC
            LIMIT 10
        """, (two_days_ago,))
        convergence = [dict(r) for r in cursor.fetchall()]
        raw["convergence"] = convergence

        # ================================================================
        # DORMANT WINNERS: Consistent Winners inactive 14+ days, now active
        # ================================================================
        fourteen_days_ago = (now - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            SELECT wlc.wallet_address, wlc.total_pnl_usd, wlc.home_runs, wlc.tokens_traded,
                   MAX(t.analysis_timestamp) as last_seen
            FROM wallet_leaderboard_cache wlc
            JOIN wallet_tags wt ON wt.wallet_address = wlc.wallet_address AND wt.tag = 'Consistent Winner'
            JOIN early_buyer_wallets ebw ON ebw.wallet_address = wlc.wallet_address
            JOIN analyzed_tokens t ON t.id = ebw.token_id AND (t.deleted_at IS NULL OR t.deleted_at = '')
            GROUP BY wlc.wallet_address
            HAVING last_seen >= ? AND wlc.total_pnl_usd > 500
            ORDER BY wlc.total_pnl_usd DESC
            LIMIT 20
        """, (two_days_ago,))
        dormant_now_active = [dict(r) for r in cursor.fetchall()]
        raw["dormant_active"] = dormant_now_active

        # ================================================================
        # DEPLOYER WATCH: High win-rate deployers with recent launches
        # ================================================================
        cursor.execute("""
            SELECT t.deployer_address,
                   COUNT(*) as total_deployed,
                   SUM(CASE WHEN tt.tag = 'verified-win' THEN 1 ELSE 0 END) as wins,
                   MAX(t.analysis_timestamp) as latest_launch,
                   GROUP_CONCAT(t.token_name) as token_names
            FROM analyzed_tokens t
            LEFT JOIN token_tags tt ON tt.token_id = t.id AND tt.tag = 'verified-win'
            WHERE t.deployer_address IS NOT NULL
            AND (t.deleted_at IS NULL OR t.deleted_at = '')
            GROUP BY t.deployer_address
            HAVING total_deployed >= 2 AND wins >= 1 AND latest_launch >= ?
            ORDER BY CAST(wins AS FLOAT) / total_deployed DESC
            LIMIT 10
        """, (fourteen_days_ago,))
        deployer_watch = [dict(r) for r in cursor.fetchall()]
        raw["deployer_watch"] = deployer_watch

        # ================================================================
        # COLD WALLET MIGRATIONS: High-PnL wallets with no recent activity
        # ================================================================
        cursor.execute("""
            SELECT wlc.wallet_address, wlc.total_pnl_usd, wlc.home_runs, wlc.tokens_traded,
                   wec.funded_by_json
            FROM wallet_leaderboard_cache wlc
            LEFT JOIN wallet_enrichment_cache wec ON wec.wallet_address = wlc.wallet_address
            WHERE wlc.total_pnl_usd > 2000
            AND wlc.wallet_address NOT IN (
                SELECT DISTINCT ebw.wallet_address FROM early_buyer_wallets ebw
                JOIN analyzed_tokens t ON t.id = ebw.token_id
                WHERE t.analysis_timestamp >= ?
            )
            ORDER BY wlc.total_pnl_usd DESC
            LIMIT 15
        """, (fourteen_days_ago,))
        cold_wallets = [dict(r) for r in cursor.fetchall()]
        raw["cold_wallets"] = cold_wallets

        # ================================================================
        # METEORA ALERTS: Tokens with stealth sell or unanalyzed pools
        # ================================================================
        cursor.execute("""
            SELECT id, token_name, token_address, has_meteora_pool,
                   meteora_creator_linked, meteora_link_type, meteora_pool_creator,
                   meteora_lp_activity_json
            FROM analyzed_tokens
            WHERE has_meteora_pool = 1 AND (deleted_at IS NULL OR deleted_at = '')
            ORDER BY analysis_timestamp DESC
            LIMIT 15
        """)
        meteora_tokens = [dict(r) for r in cursor.fetchall()]
        raw["meteora_tokens"] = meteora_tokens

        # ================================================================
        # ALLOWLIST CANDIDATES: Wallets with high resolved win quality
        # Low rug overlap, real PnL, selective participation, recent activity
        # ================================================================
        # Fetch a wider pool, then filter in Python for quality thresholds
        cursor.execute("""
            SELECT wlc.wallet_address, wlc.total_pnl_usd, wlc.realized_pnl_usd,
                   wlc.tokens_traded, wlc.tokens_won, wlc.tokens_lost, wlc.win_rate,
                   wlc.home_runs, wlc.rugs, wlc.avg_entry_seconds, wlc.tags_json,
                   wlc.wallet_balance_usd,
                   -- Real PnL coverage
                   (SELECT COUNT(*) FROM mtew_token_positions mp
                    WHERE mp.wallet_address = wlc.wallet_address AND mp.pnl_source = 'helius_enhanced') as real_pnl_count,
                   (SELECT COUNT(*) FROM mtew_token_positions mp
                    WHERE mp.wallet_address = wlc.wallet_address) as total_positions,
                   -- Rug exposure
                   (SELECT COUNT(*) FROM early_buyer_wallets eb
                    JOIN token_tags tt ON tt.token_id = eb.token_id AND tt.tag = 'verified-loss'
                    WHERE eb.wallet_address = wlc.wallet_address) as loss_tokens,
                   (SELECT COUNT(*) FROM early_buyer_wallets eb
                    JOIN token_tags tt ON tt.token_id = eb.token_id AND tt.tag IN ('verified-win', 'verified-loss')
                    WHERE eb.wallet_address = wlc.wallet_address) as resolved_tokens
            FROM wallet_leaderboard_cache wlc
            WHERE wlc.win_rate >= 0.4
            AND wlc.tokens_traded >= 5
            AND wlc.total_pnl_usd > 500
            -- Not already tagged as Sniper Bot
            AND wlc.wallet_address NOT IN (
                SELECT wallet_address FROM wallet_tags WHERE tag = 'Sniper Bot'
            )
            ORDER BY wlc.win_rate DESC, wlc.total_pnl_usd DESC
            LIMIT 60
        """)
        allowlist_raw = [dict(r) for r in cursor.fetchall()]

        # Post-filter: only keep wallets that can realistically pass Housekeeper verification
        # This prevents handing the Housekeeper 14 wallets that all get rejected
        allowlist_candidates = []
        for ac in allowlist_raw:
            real_pnl = ac.get("real_pnl_count", 0) or 0
            total_pos = ac.get("total_positions", 0) or 1
            loss = ac.get("loss_tokens", 0) or 0
            resolved = ac.get("resolved_tokens", 0) or 1
            real_coverage = real_pnl / max(total_pos, 1)
            rug_rate = loss / max(resolved, 1)

            # Minimum viable: >=50% real PnL coverage, <50% rug exposure, >=5 resolved tokens
            if real_coverage >= 0.5 and rug_rate < 0.5 and resolved >= 5:
                allowlist_candidates.append(ac)
            if len(allowlist_candidates) >= 15:
                break

        # If strict filter produces nothing, fall back to best-available with relaxed thresholds
        if not allowlist_candidates:
            for ac in allowlist_raw[:10]:
                real_pnl = ac.get("real_pnl_count", 0) or 0
                total_pos = ac.get("total_positions", 0) or 1
                loss = ac.get("loss_tokens", 0) or 0
                resolved = ac.get("resolved_tokens", 0) or 1
                real_coverage = real_pnl / max(total_pos, 1)
                rug_rate = loss / max(resolved, 1)
                # Relaxed: mark them but let Housekeeper know they're borderline
                ac["_borderline"] = True
                ac["_filter_note"] = f"Below strict threshold: real_pnl={real_coverage:.0%}, rug={rug_rate:.0%}"
                allowlist_candidates.append(ac)

        # Last-resort fallback: if even the relaxed pool was empty (allowlist_raw=[]),
        # take top wallets by PnL with at least 1 resolved token. Housekeeper still
        # gets *something* to verify, even if the verdict is "none of these qualify."
        # Without this, Housekeeper's user prompt has no candidate_data block and
        # produces an empty wallet_reliability array — which looks like a broken run.
        if not allowlist_candidates:
            cursor.execute("""
                SELECT wlc.wallet_address, wlc.total_pnl_usd, wlc.realized_pnl_usd,
                       wlc.tokens_traded, wlc.tokens_won, wlc.tokens_lost, wlc.win_rate,
                       wlc.home_runs, wlc.rugs, wlc.avg_entry_seconds, wlc.tags_json,
                       wlc.wallet_balance_usd,
                       (SELECT COUNT(*) FROM mtew_token_positions mp
                        WHERE mp.wallet_address = wlc.wallet_address AND mp.pnl_source = 'helius_enhanced') as real_pnl_count,
                       (SELECT COUNT(*) FROM mtew_token_positions mp
                        WHERE mp.wallet_address = wlc.wallet_address) as total_positions,
                       (SELECT COUNT(*) FROM early_buyer_wallets eb
                        JOIN token_tags tt ON tt.token_id = eb.token_id AND tt.tag = 'verified-loss'
                        WHERE eb.wallet_address = wlc.wallet_address) as loss_tokens,
                       (SELECT COUNT(*) FROM early_buyer_wallets eb
                        JOIN token_tags tt ON tt.token_id = eb.token_id AND tt.tag IN ('verified-win', 'verified-loss')
                        WHERE eb.wallet_address = wlc.wallet_address) as resolved_tokens
                FROM wallet_leaderboard_cache wlc
                WHERE wlc.total_pnl_usd > 0
                AND EXISTS (
                    SELECT 1 FROM early_buyer_wallets eb
                    JOIN token_tags tt ON tt.token_id = eb.token_id AND tt.tag IN ('verified-win', 'verified-loss')
                    WHERE eb.wallet_address = wlc.wallet_address
                )
                ORDER BY wlc.total_pnl_usd DESC
                LIMIT 5
            """)
            for ac in (dict(r) for r in cursor.fetchall()):
                real_pnl = ac.get("real_pnl_count", 0) or 0
                total_pos = ac.get("total_positions", 0) or 1
                loss = ac.get("loss_tokens", 0) or 0
                resolved = ac.get("resolved_tokens", 0) or 1
                real_coverage = real_pnl / max(total_pos, 1)
                rug_rate = loss / max(resolved, 1)
                ac["_borderline"] = True
                ac["_filter_note"] = (
                    f"Last-resort sample (no wallets met allowlist thresholds): "
                    f"real_pnl={real_coverage:.0%}, rug={rug_rate:.0%}, resolved={resolved}"
                )
                allowlist_candidates.append(ac)

        # Enrich allowlist candidates with fields Housekeeper needs
        # so it doesn't have to query for them
        if allowlist_candidates:
            addrs = [ac["wallet_address"] for ac in allowlist_candidates]
            placeholders = ",".join("?" for _ in addrs)

            # Sniper Bot status
            cursor.execute(
                f"SELECT wallet_address FROM wallet_tags WHERE tag = 'Sniper Bot' AND wallet_address IN ({placeholders})",
                addrs,
            )
            sniper_bots = {r[0] for r in cursor.fetchall()}

            # Funding data existence
            cursor.execute(
                f"SELECT wallet_address FROM wallet_enrichment_cache WHERE funded_by_json IS NOT NULL AND wallet_address IN ({placeholders})",
                addrs,
            )
            has_funding = {r[0] for r in cursor.fetchall()}

            # Last seen (most recent token appearance)
            cursor.execute(f"""
                SELECT ebw.wallet_address, MAX(t.analysis_timestamp) as last_seen
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens t ON t.id = ebw.token_id AND (t.deleted_at IS NULL OR t.deleted_at = '')
                WHERE ebw.wallet_address IN ({placeholders})
                GROUP BY ebw.wallet_address
            """, addrs)
            last_seen_map = {r[0]: r[1] for r in cursor.fetchall()}

            # Unresolved token count
            cursor.execute(f"""
                SELECT ebw.wallet_address, COUNT(DISTINCT ebw.token_id) as unresolved
                FROM early_buyer_wallets ebw
                WHERE ebw.wallet_address IN ({placeholders})
                AND ebw.token_id NOT IN (
                    SELECT token_id FROM token_tags WHERE tag IN ('verified-win', 'verified-loss')
                )
                GROUP BY ebw.wallet_address
            """, addrs)
            unresolved_map = {r[0]: r[1] for r in cursor.fetchall()}

            for ac in allowlist_candidates:
                addr = ac["wallet_address"]
                ac["is_sniper_bot"] = addr in sniper_bots
                ac["has_funding_data"] = addr in has_funding
                ac["last_seen"] = last_seen_map.get(addr)
                ac["unresolved_tokens"] = unresolved_map.get(addr, 0)
                resolved = ac.get("resolved_tokens", 0) or 0
                total_app = resolved + ac["unresolved_tokens"]
                ac["unresolved_share"] = round(ac["unresolved_tokens"] / max(total_app, 1), 2)
                real_pnl = ac.get("real_pnl_count", 0) or 0
                total_pos = ac.get("total_positions", 0) or 1
                ac["real_pnl_coverage"] = round(real_pnl / max(total_pos, 1), 2)
                loss = ac.get("loss_tokens", 0) or 0
                ac["rug_exposure"] = round(loss / max(resolved, 1), 2)

        raw["allowlist_candidates"] = allowlist_candidates

        # ================================================================
        # DENYLIST CANDIDATES: Toxic-flow, repeated suspicious clusters
        # Fresh-funded clusters near creation, deployer-linked buyers,
        # wallets that appear primarily on crash charts
        # ================================================================

        # Wallets with very high rug exposure (appear mostly on verified-loss tokens)
        cursor.execute("""
            SELECT eb.wallet_address,
                   COUNT(DISTINCT eb.token_id) as total_appearances,
                   SUM(CASE WHEN tt.tag = 'verified-loss' THEN 1 ELSE 0 END) as loss_appearances,
                   SUM(CASE WHEN tt.tag = 'verified-win' THEN 1 ELSE 0 END) as win_appearances,
                   wlc.total_pnl_usd, wlc.tags_json
            FROM early_buyer_wallets eb
            JOIN token_tags tt ON tt.token_id = eb.token_id AND tt.tag IN ('verified-win', 'verified-loss')
            LEFT JOIN wallet_leaderboard_cache wlc ON wlc.wallet_address = eb.wallet_address
            GROUP BY eb.wallet_address
            HAVING total_appearances >= 5
            AND CAST(loss_appearances AS FLOAT) / total_appearances >= 0.7
            ORDER BY loss_appearances DESC
            LIMIT 20
        """)
        high_rug_wallets = [dict(r) for r in cursor.fetchall()]
        raw["high_rug_wallets"] = high_rug_wallets

        # Deployer-linked buyers: wallets that share a funder with a deployer
        cursor.execute("""
            SELECT eb.wallet_address, t.deployer_address, t.token_name, t.token_address,
                   wec_buyer.funded_by_json as buyer_funding,
                   wec_deployer.funded_by_json as deployer_funding
            FROM early_buyer_wallets eb
            JOIN analyzed_tokens t ON t.id = eb.token_id AND (t.deleted_at IS NULL OR t.deleted_at = '')
            LEFT JOIN wallet_enrichment_cache wec_buyer ON wec_buyer.wallet_address = eb.wallet_address
            LEFT JOIN wallet_enrichment_cache wec_deployer ON wec_deployer.wallet_address = t.deployer_address
            WHERE t.deployer_address IS NOT NULL
            AND wec_buyer.funded_by_json IS NOT NULL
            AND wec_deployer.funded_by_json IS NOT NULL
            AND t.analysis_timestamp >= ?
            ORDER BY t.analysis_timestamp DESC
            LIMIT 50
        """, (fourteen_days_ago,))
        deployer_buyer_links_raw = [dict(r) for r in cursor.fetchall()]
        # Filter to those that actually share a funder
        deployer_linked_buyers = []
        for row in deployer_buyer_links_raw:
            try:
                bf = json.loads(row.get("buyer_funding") or "{}")
                df = json.loads(row.get("deployer_funding") or "{}")
                buyer_funder = bf.get("funder", "")
                deployer_funder = df.get("funder", "")
                if buyer_funder and deployer_funder and buyer_funder == deployer_funder:
                    row["shared_funder"] = buyer_funder
                    deployer_linked_buyers.append(row)
            except (json.JSONDecodeError, TypeError):
                continue
        raw["deployer_linked_buyers"] = deployer_linked_buyers[:15]

        # Fresh wallets with cluster tags — potential sybil/coordinated groups
        cursor.execute("""
            SELECT wt.wallet_address, GROUP_CONCAT(DISTINCT wt.tag) as tags,
                   COUNT(DISTINCT eb.token_id) as token_appearances,
                   wlc.total_pnl_usd
            FROM wallet_tags wt
            JOIN early_buyer_wallets eb ON eb.wallet_address = wt.wallet_address
            LEFT JOIN wallet_leaderboard_cache wlc ON wlc.wallet_address = wt.wallet_address
            WHERE wt.tag IN ('Cluster', 'Fresh at Entry (<24h)', 'Fresh at Entry (<1h)')
            GROUP BY wt.wallet_address
            HAVING COUNT(DISTINCT wt.tag) >= 2
            ORDER BY token_appearances DESC
            LIMIT 20
        """)
        fresh_cluster_wallets = [dict(r) for r in cursor.fetchall()]
        raw["fresh_cluster_wallets"] = fresh_cluster_wallets

        # ================================================================
        # DATA QUALITY FLAGS (for Housekeeper)
        # ================================================================
        # Tokens with pending verdicts that are old enough to have one
        cursor.execute("""
            SELECT id, token_name, token_address, analysis_timestamp, market_cap_usd, market_cap_usd_current
            FROM analyzed_tokens
            WHERE (deleted_at IS NULL OR deleted_at = '')
            AND id NOT IN (SELECT token_id FROM token_tags WHERE tag IN ('verified-win', 'verified-loss'))
            AND analysis_timestamp < ?
            LIMIT 20
        """, (fourteen_days_ago,))
        pending_verdicts = [dict(r) for r in cursor.fetchall()]
        raw["pending_verdicts"] = pending_verdicts

        # Wallets with estimated PnL that could be upgraded to real
        cursor.execute("""
            SELECT wallet_address, COUNT(*) as estimated_positions
            FROM mtew_token_positions
            WHERE pnl_source = 'estimated' OR pnl_source IS NULL
            GROUP BY wallet_address
            HAVING estimated_positions >= 3
            ORDER BY estimated_positions DESC
            LIMIT 20
        """)
        needs_pnl_upgrade = [dict(r) for r in cursor.fetchall()]
        raw["needs_pnl_upgrade"] = needs_pnl_upgrade

        # Win multiplier verification candidates
        cursor.execute("""
            SELECT t.id, t.token_name, t.token_address,
                   t.market_cap_usd, t.market_cap_ath,
                   tt.tag as multiplier_tag,
                   ROUND(CAST(t.market_cap_ath AS FLOAT) / NULLIF(t.market_cap_usd, 0), 1) as actual_multiple
            FROM analyzed_tokens t
            JOIN token_tags tt ON tt.token_id = t.id AND tt.tag LIKE 'win:%'
            WHERE (t.deleted_at IS NULL OR t.deleted_at = '')
            AND t.market_cap_usd > 0
            ORDER BY t.market_cap_ath DESC
            LIMIT 20
        """)
        multiplier_check = [dict(r) for r in cursor.fetchall()]
        raw["multiplier_check"] = multiplier_check

        # Starred items for portfolio tracking
        cursor.execute("SELECT * FROM starred_items ORDER BY starred_at DESC")
        starred = [dict(r) for r in cursor.fetchall()]
        raw["starred"] = starred

    # ================================================================
    # BUILD HUMAN-READABLE SNAPSHOT
    # ================================================================
    chicago_now = now.astimezone(ZoneInfo("America/Chicago"))
    snapshot = f"""DATABASE SNAPSHOT (as of {chicago_now.strftime('%b %d, %Y %I:%M %p %Z')}):
- {total_tokens} tokens analyzed ({total_wins} wins, {total_losses} losses, {pending} pending verdicts)
- {total_wallets} recurring wallets tracked
- {starred_wallets} starred wallets, {starred_tokens} starred tokens
- Latest scan: {latest_scan}
- Top wallet PnL: {top_wallets[0]['wallet_address'][:16]}... = +${top_wallets[0]['total_pnl_usd']:,.0f} ({top_wallets[0]['tokens_traded']} tokens, {top_wallets[0]['home_runs']} home runs) if top_wallets else 'N/A'
- {len(recently_active_profitable)} profitable wallets active in last 48h
- {len(convergence)} tokens with 3+ Consistent Winners buying
- {len(deployer_watch)} high win-rate deployers with recent launches
- {len(cold_wallets)} high-PnL wallets gone cold (14+ days inactive)
- {len(meteora_tokens)} tokens with Meteora pools detected
- {len(allowlist_candidates)} allowlist candidates (high win quality, low rug exposure)
- {len(high_rug_wallets)} denylist candidates (high rug exposure wallets)
- {len(deployer_linked_buyers)} deployer-linked buyer pairs detected
- {len(fresh_cluster_wallets)} fresh+cluster wallets (potential sybil)
"""

    # ================================================================
    # BUILD DETAILED INVESTIGATION LEADS (full data, no re-querying needed)
    # ================================================================
    leads_parts = []

    if raw.get("bot_profiles"):
        leads_parts.append("=== BOT BEHAVIOR PROFILES (computed from trade data — DO NOT RE-QUERY) ===")
        leads_parts.append("Strategy types: Sniper (block-0 entries), Scalper (fast exits, small targets),")
        leads_parts.append("  Accumulator (multiple buys per token), Runner (holds for big multiples),")
        leads_parts.append("  Spray Bot (high volume, low win rate), Copy Bot (follows other wallets)")
        leads_parts.append("Confidence tiers: HIGH = strong rule fired on >10 tokens, MEDIUM = secondary rule,")
        leads_parts.append("  TENTATIVE = small-sample (3-10 tokens) hint, LOW = Unknown (insufficient signal).")
        for bp in raw["bot_profiles"]:
            loss_cut = f"cuts at {bp['avg_loss_cut']:.0%}" if bp.get("avg_loss_cut") else "?"
            win_target = f"sells at {bp['avg_win_multiple']:.1f}x" if bp.get("avg_win_multiple") else "?"
            hold = f"{bp['avg_hold_minutes']:.0f}min avg hold" if bp.get("avg_hold_minutes") else "?"
            entry = f"{bp['avg_entry_seconds']:.0f}s avg entry" if bp.get("avg_entry_seconds") else "?"
            infra = f" | Infra: {bp['infra_tags']}" if bp.get("infra_tags") else ""
            conf = (bp.get("strategy_confidence") or "low").upper()
            leads_parts.append(
                f"  {bp['wallet_address']} | {bp['strategy']} [{conf}] | "
                f"{bp['win_rate']:.0f}% WR ({bp['tokens_traded']} tokens) | "
                f"{entry} | {hold} | {win_target} | {loss_cut} | "
                f"avg size ${bp['avg_position_size_usd']:,.0f}{infra}"
            )
        leads_parts.append("  USE THESE PROFILES when classifying wallets — a Scalper with 45% WR and $5K/day is NOT toxic flow.")
        leads_parts.append("  TENTATIVE profiles are hints from small samples — treat as signal, not verdict.")
        leads_parts.append("")

    if convergence:
        leads_parts.append("=== CONVERGENCE ALERTS (DO NOT RE-QUERY — all converging wallets listed inline) ===")
        for c in convergence[:5]:
            winner_addrs = [a.strip() for a in (c.get('winner_wallets') or '').split(',') if a.strip()]
            leads_parts.append(f"\nToken: {c['token_name']} | {c['token_address']}")
            leads_parts.append(f"  MC: ${c.get('market_cap_usd_current', 0):,.0f} | Score: {c.get('score_composite', '?')} | Winners: {c['winner_count']}")
            for waddr in winner_addrs:
                leads_parts.append(f"    - {waddr}")
            leads_parts.append(f"  CLASSIFY: organic smart money or adversarial convergence?")

    if cold_wallets:
        leads_parts.append("\n=== COLD WALLET MIGRATIONS (DO NOT RE-QUERY — funding data inlined) ===")
        leads_parts.append("These wallets were profitable but have been inactive 14+ days. Funder shown inline.")
        for cw in cold_wallets[:8]:
            funded_by = ""
            if cw.get('funded_by_json'):
                try:
                    fb = json.loads(cw['funded_by_json'])
                    if fb.get('funder'):
                        funded_by = f" | Funded by: {fb['funder']}"
                        if fb.get('funderName'):
                            funded_by += f" ({fb['funderName']})"
                except Exception:
                    pass
            if not funded_by:
                funded_by = " | Funded by: unknown (no enrichment cache hit)"
            leads_parts.append(f"  {cw['wallet_address']} | PnL: +${cw['total_pnl_usd']:,.0f} | Home runs: {cw.get('home_runs', 0)} | Tokens: {cw.get('tokens_traded', 0)}{funded_by}")
        leads_parts.append("  CLASSIFY: shared funders across cold wallets = same operator. Forward-trace only if classification is ambiguous.")

    if deployer_watch:
        leads_parts.append("\n=== DEPLOYER WATCH (DO NOT RE-QUERY — data below is complete) ===")
        for dw in deployer_watch[:5]:
            total = dw['total_deployed']
            wins = dw['wins'] or 0
            wr = round(wins / total * 100) if total > 0 else 0
            leads_parts.append(f"  Deployer: {dw['deployer_address']} | {wins}/{total} wins ({wr}%) | Latest launch: {dw['latest_launch']}")
            leads_parts.append(f"    Tokens: {dw.get('token_names', '?')}")

    if dormant_now_active:
        leads_parts.append(f"\n=== DORMANT WINNERS NOW ACTIVE ({len(dormant_now_active)} wallets) ===")
        for d in dormant_now_active[:5]:
            leads_parts.append(f"  {d['wallet_address']} | PnL: +${d['total_pnl_usd']:,.0f} | Win rate: {d.get('win_rate', 0):.0%} | Last seen: {d.get('last_seen', '?')}")

    if meteora_tokens:
        # Compact summary only — full LP activity is in raw for bundle export, not needed in prompt
        linked_count = sum(1 for m in meteora_tokens if m.get('meteora_creator_linked'))
        leads_parts.append(f"\n=== METEORA POOLS ({len(meteora_tokens)} tokens, {linked_count} insider-linked) ===")
        for m in meteora_tokens[:3]:
            linked_str = "INSIDER LINKED" if m.get('meteora_creator_linked') else "unlinked"
            lp_count = 0
            if m.get('meteora_lp_activity_json'):
                try:
                    lp_count = len(json.loads(m['meteora_lp_activity_json']))
                except Exception:
                    pass
            leads_parts.append(f"  {m['token_name']} ({m['token_address']}) | {linked_str} | {lp_count} LP events")
        if len(meteora_tokens) > 3:
            leads_parts.append(f"  + {len(meteora_tokens) - 3} more — query analyzed_tokens WHERE has_meteora_pool = 1 if needed")

    if allowlist_candidates:
        leads_parts.append("\n=== ALLOWLIST CANDIDATES — Good Trader Discovery (DO NOT RE-QUERY) ===")
        leads_parts.append("Wallets with high win quality, low rug exposure, real PnL. Verify reliability before recommending.")
        for ac in allowlist_candidates[:15]:
            real_pct = round(ac['real_pnl_count'] / max(ac['total_positions'], 1) * 100)
            rug_rate = round(ac['loss_tokens'] / max(ac['resolved_tokens'], 1) * 100)
            tags = ""
            try:
                t = json.loads(ac.get('tags_json') or '[]')
                if t:
                    tags = f" | Tags: {', '.join(t[:4])}"
            except Exception:
                pass
            leads_parts.append(
                f"  {ac['wallet_address']} | PnL: +${ac['total_pnl_usd']:,.0f} | "
                f"Win rate: {ac['win_rate']:.0%} | Tokens: {ac['tokens_traded']} | "
                f"Home runs: {ac.get('home_runs', 0)} | Rug rate: {rug_rate}% | "
                f"Real PnL: {real_pct}% ({ac['real_pnl_count']}/{ac['total_positions']}) | "
                f"Resolved: {ac['resolved_tokens']}{tags}"
            )
        leads_parts.append("  CLASSIFY: For each, determine if suitable as anti-rug confluence signal (allowlist).")

    if high_rug_wallets:
        leads_parts.append("\n=== DENYLIST CANDIDATES — High Rug Exposure (DO NOT RE-QUERY) ===")
        leads_parts.append("Wallets appearing primarily on crash/rug tokens. Potential toxic flow or rug infrastructure.")
        for hr in high_rug_wallets:
            loss_rate = round(hr['loss_appearances'] / max(hr['total_appearances'], 1) * 100)
            leads_parts.append(
                f"  {hr['wallet_address']} | Appearances: {hr['total_appearances']} | "
                f"Losses: {hr['loss_appearances']} ({loss_rate}%) | Wins: {hr['win_appearances']} | "
                f"PnL: ${hr.get('total_pnl_usd', 0):,.0f}"
            )
        leads_parts.append("  CLASSIFY: Flag as denylist if rug exposure pattern is consistent. Check for deployer links.")

    if deployer_linked_buyers:
        leads_parts.append("\n=== DENYLIST CANDIDATES — Deployer-Linked Buyers (DO NOT RE-QUERY) ===")
        leads_parts.append("Early buyers sharing a funder with the token deployer. Likely coordinated.")
        for dl in deployer_linked_buyers:
            leads_parts.append(
                f"  Buyer: {dl['wallet_address']} | Deployer: {dl['deployer_address']} | "
                f"Token: {dl['token_name']} ({dl['token_address']}) | Shared funder: {dl['shared_funder']}"
            )
        leads_parts.append("  CLASSIFY: Flag deployer-linked buyers as denylist unless evidence shows legitimate team.")

    if fresh_cluster_wallets:
        leads_parts.append("\n=== DENYLIST CANDIDATES — Fresh + Cluster Wallets (DO NOT RE-QUERY) ===")
        leads_parts.append("Wallets tagged both Fresh and Cluster — potential sybil groups.")
        for fc in fresh_cluster_wallets:
            leads_parts.append(
                f"  {fc['wallet_address']} | Tags: {fc['tags']} | Appearances: {fc['token_appearances']} | "
                f"PnL: ${fc.get('total_pnl_usd', 0):,.0f}"
            )
        leads_parts.append("  CLASSIFY: Flag as denylist if pattern repeats across multiple tokens.")

    if raw.get("starred") and len(raw["starred"]) > 0:
        leads_parts.append("\n=== STARRED ITEMS (DO NOT RE-QUERY — data below is complete) ===")
        for s in raw["starred"]:
            leads_parts.append(f"  {s['item_type']}: {s['item_address']} | Name: {s.get('nametag') or 'unnamed'} | Starred: {s.get('starred_at', '?')}")

    # Data quality leads for Housekeeper
    quality_parts = []
    if pending_verdicts:
        quality_parts.append(f"PENDING VERDICTS: {len(pending_verdicts)} tokens older than 14 days still have no verdict")
    if needs_pnl_upgrade:
        quality_parts.append(f"ESTIMATED PNL: {len(needs_pnl_upgrade)} wallets have 3+ positions with estimated (not real) PnL")
    if multiplier_check:
        quality_parts.append(f"MULTIPLIER VERIFICATION: {len(multiplier_check)} win multiplier tags to verify against actual ATH/MC ratios")

    leads = "\n".join(leads_parts)
    quality = "\n".join(quality_parts)

    log_info(
        f"[IntelPrecompute] Snapshot generated: {total_tokens} tokens, {total_wallets} wallets, "
        f"{len(convergence)} convergence, {len(cold_wallets)} cold wallets, "
        f"{len(allowlist_candidates)} allowlist, {len(high_rug_wallets)} denylist"
    )

    # Strip heavy fields from raw before storage (LP activity JSON dominates bundle size)
    # Keep summary counts but drop the full event arrays
    if raw.get("meteora_tokens"):
        for m in raw["meteora_tokens"]:
            lp_json = m.pop("meteora_lp_activity_json", None)
            m["lp_event_count"] = 0
            if lp_json:
                try:
                    m["lp_event_count"] = len(json.loads(lp_json))
                except (json.JSONDecodeError, TypeError):
                    pass

    # Strip funded_by_json from cold wallets (already shown in leads text)
    if raw.get("cold_wallets"):
        for cw in raw["cold_wallets"]:
            fb_json = cw.pop("funded_by_json", None)
            if fb_json:
                try:
                    fb = json.loads(fb_json)
                    cw["funder"] = fb.get("funder")
                    cw["funder_name"] = fb.get("funderName")
                except (json.JSONDecodeError, TypeError):
                    pass

    # Strip full funding JSON from deployer-linked buyers (keep shared_funder)
    if raw.get("deployer_linked_buyers"):
        for dl in raw["deployer_linked_buyers"]:
            dl.pop("buyer_funding", None)
            dl.pop("deployer_funding", None)

    # Strip winner_wallets full string from convergence (keep count)
    if raw.get("convergence"):
        for c in raw["convergence"]:
            wallets_str = c.pop("winner_wallets", "")
            c["winner_wallet_sample"] = [a.strip() for a in (wallets_str or "").split(",")[:5] if a.strip()]

    return {
        "snapshot": snapshot,
        "leads": leads,
        "quality_flags": quality,
        "raw": raw,
    }


def generate_forensics_packet(limit: int = 10) -> Dict[str, Any]:
    """
    Build forensic casefiles for top-PnL leaderboard wallets.

    For each wallet, assembles:
    - PnL breakdown (realized vs unrealized, concentration)
    - Best trade details (token, entry, exit, chart metrics)
    - Contamination signals (deployer, cluster, sniper bot, fresh)
    - Position state (open, partial, exited)
    - Trail status (active, cold, migrated)
    - Leaderboard truth assessment data

    Returns structured casefiles ready for Housekeeper verification
    and Investigator classification.
    """
    now = datetime.now(timezone.utc)
    casefiles = []

    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get top PnL wallets
        cursor.execute("""
            SELECT wallet_address, total_pnl_usd, realized_pnl_usd, tokens_traded,
                   tokens_won, tokens_lost, win_rate, home_runs, rugs, tier_score,
                   avg_entry_seconds, avg_hold_hours_7d, wallet_balance_usd, tags_json
            FROM wallet_leaderboard_cache
            ORDER BY total_pnl_usd DESC
            LIMIT ?
        """, (limit,))
        top_wallets = [dict(r) for r in cursor.fetchall()]

        for wallet in top_wallets:
            addr = wallet["wallet_address"]
            total_pnl = wallet["total_pnl_usd"] or 0
            realized_pnl = wallet["realized_pnl_usd"] or 0

            # ---- PnL Breakdown ----
            unrealized = total_pnl - realized_pnl
            realized_share = abs(realized_pnl) / max(abs(total_pnl), 1)
            is_mostly_unrealized = unrealized > 0 and unrealized > abs(realized_pnl) * 2

            # ---- Best Trade (highest PnL token) ----
            cursor.execute("""
                SELECT mp.token_id, mp.total_bought_usd, mp.total_sold_usd, mp.realized_pnl,
                       mp.still_holding, mp.entry_timestamp, mp.exit_detected_at,
                       mp.last_sell_timestamp, mp.pnl_source, mp.buy_count, mp.sell_count,
                       at.token_name, at.token_address, at.market_cap_usd, at.market_cap_usd_current,
                       at.market_cap_ath, at.deployer_address, at.analysis_timestamp,
                       at.has_meteora_pool, at.bundle_cluster_count, at.stealth_holder_count,
                       at.fresh_wallet_pct, at.controlled_supply_score
                FROM mtew_token_positions mp
                JOIN analyzed_tokens at ON at.id = mp.token_id
                WHERE mp.wallet_address = ?
                ORDER BY mp.realized_pnl DESC
                LIMIT 3
            """, (addr,))
            best_trades = [dict(r) for r in cursor.fetchall()]

            best_trade = best_trades[0] if best_trades else None
            best_trade_pnl = best_trade["realized_pnl"] if best_trade else 0
            profit_concentration = abs(best_trade_pnl) / max(abs(realized_pnl), 1) if best_trade and realized_pnl != 0 else 0

            # ---- Position State ----
            cursor.execute("""
                SELECT COUNT(*) as total, SUM(CASE WHEN still_holding = 1 THEN 1 ELSE 0 END) as holding
                FROM mtew_token_positions WHERE wallet_address = ?
            """, (addr,))
            pos_row = cursor.fetchone()
            total_positions = pos_row["total"] if pos_row else 0
            holding_count = pos_row["holding"] if pos_row else 0
            if total_positions == 0:
                position_state = "no_data"
            elif holding_count == 0:
                position_state = "fully_exited"
            elif holding_count == total_positions:
                position_state = "all_open"
            else:
                position_state = "partial"

            # ---- Tags / Contamination ----
            cursor.execute("SELECT tag FROM wallet_tags WHERE wallet_address = ?", (addr,))
            tags = [r["tag"] for r in cursor.fetchall()]
            is_deployer = any(t in tags for t in ["Deployer", "Serial Deployer"])
            is_cluster = "Cluster" in tags
            is_sniper_bot = "Sniper Bot" in tags
            is_fresh = any("Fresh" in t for t in tags)
            is_jito = "Bundled (Jito)" in tags

            # ---- Funding ----
            cursor.execute("SELECT funded_by_json FROM wallet_enrichment_cache WHERE wallet_address = ?", (addr,))
            funding_row = cursor.fetchone()
            funder = None
            funder_name = None
            if funding_row and funding_row["funded_by_json"]:
                try:
                    fb = json.loads(funding_row["funded_by_json"])
                    funder = fb.get("funder")
                    funder_name = fb.get("funderName")
                except (json.JSONDecodeError, TypeError):
                    pass

            # ---- Last Activity ----
            cursor.execute("""
                SELECT MAX(t.analysis_timestamp) as last_seen
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens t ON t.id = ebw.token_id
                WHERE ebw.wallet_address = ? AND (t.deleted_at IS NULL OR t.deleted_at = '')
            """, (addr,))
            ls_row = cursor.fetchone()
            last_seen = ls_row["last_seen"] if ls_row else None

            fourteen_days_ago = (now - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
            is_cold = last_seen is not None and last_seen < fourteen_days_ago
            is_active = last_seen is not None and last_seen >= fourteen_days_ago

            # ---- Real PnL Coverage ----
            cursor.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN pnl_source = 'helius_enhanced' THEN 1 ELSE 0 END) as real_count
                FROM mtew_token_positions WHERE wallet_address = ?
            """, (addr,))
            pnl_row = cursor.fetchone()
            real_pnl_count = pnl_row["real_count"] if pnl_row else 0
            total_pos_count = pnl_row["total"] if pnl_row else 0
            real_pnl_coverage = real_pnl_count / max(total_pos_count, 1)

            # ---- Leaderboard Truth ----
            if real_pnl_coverage < 0.3:
                leaderboard_truth = "contaminated"
            elif is_mostly_unrealized:
                leaderboard_truth = "mark_to_market_heavy"
            elif realized_share < 0.5:
                leaderboard_truth = "mixed"
            else:
                leaderboard_truth = "realized"

            # ---- Best trade chart metrics ----
            best_trade_summary = None
            if best_trade:
                scan_mc = best_trade["market_cap_usd"] or 0
                ath = best_trade["market_cap_ath"] or 0
                current_mc = best_trade["market_cap_usd_current"] or 0
                ath_multiple = round(ath / max(scan_mc, 1), 1)
                current_vs_ath = round(current_mc / max(ath, 1), 2)
                best_trade_summary = {
                    "token_name": best_trade["token_name"],
                    "token_address": best_trade["token_address"],
                    "realized_pnl": best_trade["realized_pnl"],
                    "bought_usd": best_trade["total_bought_usd"],
                    "sold_usd": best_trade["total_sold_usd"],
                    "still_holding": bool(best_trade["still_holding"]),
                    "pnl_source": best_trade["pnl_source"],
                    "buy_count": best_trade["buy_count"],
                    "sell_count": best_trade["sell_count"],
                    "scan_mc": scan_mc,
                    "ath": ath,
                    "current_mc": current_mc,
                    "ath_multiple": ath_multiple,
                    "current_vs_ath": current_vs_ath,
                    "deployer_address": best_trade["deployer_address"],
                    "has_meteora_pool": bool(best_trade["has_meteora_pool"]),
                    "bundle_cluster_count": best_trade["bundle_cluster_count"],
                    "fresh_wallet_pct": best_trade["fresh_wallet_pct"],
                    "controlled_supply_score": best_trade["controlled_supply_score"],
                }

            casefile = {
                "wallet_address": addr,
                "total_pnl_usd": total_pnl,
                "realized_pnl_usd": realized_pnl,
                "unrealized_pnl_usd": round(unrealized, 2),
                "realized_share": round(realized_share, 2),
                "tokens_traded": wallet["tokens_traded"],
                "win_rate": wallet["win_rate"],
                "home_runs": wallet["home_runs"],
                "avg_entry_seconds": wallet["avg_entry_seconds"],
                "profit_concentration": round(profit_concentration, 2),
                "position_state": position_state,
                "leaderboard_truth": leaderboard_truth,
                "real_pnl_coverage": round(real_pnl_coverage, 2),
                "is_deployer": is_deployer,
                "is_cluster": is_cluster,
                "is_sniper_bot": is_sniper_bot,
                "is_fresh": is_fresh,
                "is_jito": is_jito,
                "tags": tags,
                "funder": funder,
                "funder_name": funder_name,
                "last_seen": last_seen,
                "trail_status": "cold" if is_cold else ("active" if is_active else "unknown"),
                "best_trade": best_trade_summary,
            }
            casefiles.append(casefile)

    log_info(f"[IntelPrecompute] Forensics packet: {len(casefiles)} casefiles built")

    # Build human-readable leads
    chicago_now = datetime.now(ZoneInfo("America/Chicago"))
    leads_parts = [f"=== TOP PnL FORENSIC CASEFILES (as of {chicago_now.strftime('%b %d, %Y %I:%M %p %Z')}) ==="]
    leads_parts.append(f"Analyzing top {len(casefiles)} wallets by total PnL. Classify each.\n")

    for i, cf in enumerate(casefiles, 1):
        leads_parts.append(f"--- CASEFILE #{i}: {cf['wallet_address']} ---")
        leads_parts.append(f"  Total PnL: ${cf['total_pnl_usd']:,.0f} | Realized: ${cf['realized_pnl_usd']:,.0f} | Unrealized: ${cf['unrealized_pnl_usd']:,.0f}")
        leads_parts.append(f"  Realized share: {cf['realized_share']:.0%} | Leaderboard truth: {cf['leaderboard_truth']}")
        leads_parts.append(f"  Tokens: {cf['tokens_traded']} | Win rate: {cf['win_rate']:.0%} | Home runs: {cf['home_runs']} | Avg entry: {cf['avg_entry_seconds']}s")
        leads_parts.append(f"  Position state: {cf['position_state']} | Trail: {cf['trail_status']} | Real PnL coverage: {cf['real_pnl_coverage']:.0%}")
        leads_parts.append(f"  Profit concentration in best trade: {cf['profit_concentration']:.0%}")

        contam = []
        if cf["is_deployer"]: contam.append("DEPLOYER")
        if cf["is_cluster"]: contam.append("CLUSTER")
        if cf["is_sniper_bot"]: contam.append("SNIPER_BOT")
        if cf["is_fresh"]: contam.append("FRESH")
        if cf["is_jito"]: contam.append("JITO_BUNDLED")
        leads_parts.append(f"  Contamination: {', '.join(contam) if contam else 'none'}")
        leads_parts.append(f"  Tags: {', '.join(cf['tags']) if cf['tags'] else 'none'}")

        if cf.get("funder"):
            name = f" ({cf['funder_name']})" if cf.get("funder_name") else ""
            leads_parts.append(f"  Funder: {cf['funder']}{name}")

        bt = cf.get("best_trade")
        if bt:
            leads_parts.append(f"  BEST TRADE: {bt['token_name']} ({bt['token_address']})")
            leads_parts.append(f"    Bought: ${bt['bought_usd']:,.0f} | Sold: ${bt['sold_usd']:,.0f} | PnL: ${bt['realized_pnl']:,.0f} | Still holding: {bt['still_holding']}")
            leads_parts.append(f"    Scan MC: ${bt['scan_mc']:,.0f} | ATH: ${bt['ath']:,.0f} ({bt['ath_multiple']}x) | Current: ${bt['current_mc']:,.0f} ({bt['current_vs_ath']:.0%} of ATH)")
            leads_parts.append(f"    Meteora: {bt['has_meteora_pool']} | Bundles: {bt['bundle_cluster_count']} | Fresh%: {bt['fresh_wallet_pct']} | Controlled: {bt['controlled_supply_score']}")
            if bt.get("deployer_address"):
                leads_parts.append(f"    Token deployer: {bt['deployer_address']}")

        leads_parts.append(f"  CLASSIFY: repeatable_operator / single_home_run / open_position_mirage / deployer_or_team_linked / coordinated_setup_beneficiary / wash_amplified / unclear")
        leads_parts.append("")

    return {
        "casefiles": casefiles,
        "leads": "\n".join(leads_parts),
        "count": len(casefiles),
    }
