"""
Follow-Up Tracker (Stage 0.5)

After a token's watch window closes in the Real-Time Token Feed,
this tracker continues monitoring its MC trajectory via DexScreener (free).

Features:
  - Adaptive observation: extends tracking if MC is trending up, cuts short if flat/dead
  - Stores MC trajectory as timestamped readings
  - Updates conviction labels as MC changes
  - Hands off naturally when data becomes boring (flatline/crash)
  - Rate limit awareness: tracks DexScreener call rate

Settings (from ingest_settings):
  - followup_enabled: bool (default True)
  - followup_max_duration_minutes: int (default 120)
  - followup_check_interval_seconds: int (default 120)
  - followup_auto_extend_uptrend: bool (default True)
  - followup_auto_cut_flatline: bool (default True)
  - followup_track_statuses: list (default ["high_conviction", "watching"])
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict

from meridinate.observability import log_error, log_info


@dataclass
class TrajectoryReading:
    timestamp: str
    mc: float
    minutes_since_creation: float


@dataclass
class TrackedToken:
    token_address: str
    token_name: Optional[str]
    status: str  # from RTTF
    conviction_score: int
    start_time: float  # unix timestamp when tracking started
    creation_time: float  # unix timestamp of token creation
    trajectory: List[TrajectoryReading] = field(default_factory=list)
    peak_mc: float = 0.0
    peak_mc_at: Optional[str] = None
    peak_minutes: float = 0.0
    last_check: float = 0.0
    consecutive_flat: int = 0  # count of consecutive flat readings
    stopped: bool = False
    stop_reason: Optional[str] = None

    def to_dict(self):
        return {
            **{k: v for k, v in asdict(self).items() if k != 'trajectory'},
            'trajectory': [asdict(r) for r in self.trajectory],
            'readings_count': len(self.trajectory),
            'current_mc': self.trajectory[-1].mc if self.trajectory else 0,
            'tracking_minutes': (time.time() - self.start_time) / 60,
        }


class FollowUpTracker:
    """
    Tracks MC trajectory for tokens after their RTTF watch window closes.
    Runs as an async background task.
    """

    def __init__(self):
        self._tracking: Dict[str, TrackedToken] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._dex_calls_last_minute: List[float] = []  # timestamps of recent calls
        self._stats = {
            "active_tracking": 0,
            "total_tracked": 0,
            "total_completed": 0,
            "dex_calls_per_minute": 0,
            "rate_limited": False,
        }

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stats(self) -> dict:
        self._stats["active_tracking"] = len([t for t in self._tracking.values() if not t.stopped])
        self._stats["dex_calls_per_minute"] = self._count_recent_calls()
        return self._stats.copy()

    def get_tracked_tokens(self, limit: int = 50) -> List[dict]:
        """Get currently tracked tokens, sorted by most recent activity."""
        tokens = sorted(
            self._tracking.values(),
            key=lambda t: t.last_check,
            reverse=True
        )
        return [t.to_dict() for t in tokens[:limit]]

    def _count_recent_calls(self) -> int:
        """Count DexScreener API calls in the last 60 seconds."""
        now = time.time()
        self._dex_calls_last_minute = [t for t in self._dex_calls_last_minute if now - t < 60]
        return len(self._dex_calls_last_minute)

    def _record_dex_call(self):
        """Record a DexScreener API call for rate tracking."""
        self._dex_calls_last_minute.append(time.time())

    def add_token(self, token_address: str, token_name: Optional[str],
                  status: str, conviction_score: int, creation_time: Optional[str]):
        """Add a token for follow-up tracking after its watch window closes."""
        if token_address in self._tracking:
            return  # Already tracking

        from meridinate.settings import CURRENT_INGEST_SETTINGS
        track_statuses = CURRENT_INGEST_SETTINGS.get(
            "followup_track_statuses", ["high_conviction", "watching"]
        )
        if status not in track_statuses:
            return  # Don't track this status

        creation_unix = time.time()
        if creation_time:
            try:
                ts = str(creation_time).replace('Z', '').split('+')[0]
                creation_unix = datetime.fromisoformat(ts).timestamp()
            except Exception:
                pass

        tracked = TrackedToken(
            token_address=token_address,
            token_name=token_name,
            status=status,
            conviction_score=conviction_score,
            start_time=time.time(),
            creation_time=creation_unix,
        )
        self._tracking[token_address] = tracked
        self._stats["total_tracked"] += 1
        log_info(f"[FollowUp] Tracking {token_name or token_address[:12]}... (status={status}, score={conviction_score})")

    async def start(self):
        """Start the follow-up tracking loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._tracking_loop())
        log_info("[FollowUp] Started")

    async def stop(self):
        """Stop the follow-up tracking loop. Persists all in-progress trajectories."""
        self._running = False

        # Save all active trajectories before stopping
        active = [t for t in self._tracking.values() if not t.stopped and len(t.trajectory) > 0]
        for tracked in active:
            tracked.stopped = True
            tracked.stop_reason = "Meridinate shutdown — partial trajectory saved"
            self._persist_lifecycle(tracked)
        if active:
            log_info(f"[FollowUp] Saved {len(active)} in-progress trajectories before shutdown")

        if self._task and not self._task.done():
            self._task.cancel()
        log_info("[FollowUp] Stopped")

    async def _tracking_loop(self):
        """Main loop — checks each tracked token at its interval."""
        while self._running:
            try:
                from meridinate.settings import CURRENT_INGEST_SETTINGS
                interval = CURRENT_INGEST_SETTINGS.get("followup_check_interval_seconds", 120)
                max_duration = CURRENT_INGEST_SETTINGS.get("followup_max_duration_minutes", 120)
                auto_extend = CURRENT_INGEST_SETTINGS.get("followup_auto_extend_uptrend", True)
                auto_cut = CURRENT_INGEST_SETTINGS.get("followup_auto_cut_flatline", True)
                mc_threshold = CURRENT_INGEST_SETTINGS.get("realtime_mc_min_at_close", 5000)

                now = time.time()

                for addr, tracked in list(self._tracking.items()):
                    if tracked.stopped:
                        continue

                    # Check if due for a reading
                    if now - tracked.last_check < interval:
                        continue

                    # Check rate limit (stay under 50/min to be safe)
                    if self._count_recent_calls() >= 50:
                        self._stats["rate_limited"] = True
                        break  # Wait for next loop iteration
                    else:
                        self._stats["rate_limited"] = False

                    # Fetch MC from DexScreener
                    mc = await asyncio.to_thread(self._fetch_mc, addr)
                    self._record_dex_call()
                    tracked.last_check = now

                    if mc is None or mc <= 0:
                        continue

                    # Record reading
                    minutes_since = (now - tracked.creation_time) / 60
                    reading = TrajectoryReading(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        mc=mc,
                        minutes_since_creation=round(minutes_since, 1),
                    )
                    tracked.trajectory.append(reading)

                    # Update peak
                    if mc > tracked.peak_mc:
                        tracked.peak_mc = mc
                        tracked.peak_mc_at = reading.timestamp
                        tracked.peak_minutes = minutes_since

                    # Adaptive observation logic
                    tracking_minutes = (now - tracked.start_time) / 60

                    # Hard cap: max duration
                    if tracking_minutes >= max_duration:
                        tracked.stopped = True
                        tracked.stop_reason = f"Max duration reached ({max_duration} min)"
                        self._finalize_token(tracked, mc_threshold)
                        continue

                    # Auto-cut: flatline detection (5+ readings within 5% of each other)
                    if auto_cut and len(tracked.trajectory) >= 3:
                        recent = [r.mc for r in tracked.trajectory[-3:]]
                        mean_recent = sum(recent) / len(recent)
                        if mean_recent > 0:
                            max_deviation = max(abs(r - mean_recent) / mean_recent for r in recent)
                            if max_deviation < 0.05:
                                tracked.consecutive_flat += 1
                            else:
                                tracked.consecutive_flat = 0

                            if tracked.consecutive_flat >= 5:
                                tracked.stopped = True
                                tracked.stop_reason = "Flatline detected (5+ stable readings)"
                                self._finalize_token(tracked, mc_threshold)
                                continue

                    # Auto-cut: dead token (80%+ drop from peak, no recovery in 10 min)
                    if auto_cut and tracked.peak_mc > 0 and mc < tracked.peak_mc * 0.2:
                        # Check if it's been below 20% of peak for a while
                        recent_below = all(
                            r.mc < tracked.peak_mc * 0.3
                            for r in tracked.trajectory[-5:]
                        ) if len(tracked.trajectory) >= 5 else False
                        if recent_below:
                            tracked.stopped = True
                            tracked.stop_reason = f"Dead (80%+ drop from peak ${tracked.peak_mc:,.0f})"
                            self._finalize_token(tracked, mc_threshold)
                            continue

                    # Auto-extend: uptrend detection (positive slope over last 3 readings)
                    if auto_extend and len(tracked.trajectory) >= 3:
                        recent_3 = [r.mc for r in tracked.trajectory[-3:]]
                        if recent_3[-1] > recent_3[0] * 1.1:  # 10%+ growth over last 3 readings
                            # Uptrend — keep tracking (don't stop even if past soft limit)
                            pass

                    # Update status label based on current MC
                    if mc >= mc_threshold and tracked.status in ("watching", "weak"):
                        tracked.status = "high_conviction"
                        tracked.conviction_score = min(100, tracked.conviction_score + 15)
                        log_info(f"[FollowUp] ⬆️ Upgraded {tracked.token_name or addr[:12]}... to HIGH CONVICTION (MC=${mc:,.0f})")
                        self._update_webhook_detection(tracked)
                    elif mc < mc_threshold * 0.5 and tracked.status == "high_conviction":
                        tracked.status = "weak"
                        tracked.conviction_score = max(0, tracked.conviction_score - 20)
                        log_info(f"[FollowUp] ⬇️ Downgraded {tracked.token_name or addr[:12]}... to WEAK (MC=${mc:,.0f})")
                        self._update_webhook_detection(tracked)

                # Broadcast updates to frontend
                try:
                    from meridinate.websocket import broadcast_message
                    await broadcast_message({
                        "event": "followup_update",
                        "data": {
                            "active": self.stats["active_tracking"],
                            "rate": self._count_recent_calls(),
                        }
                    })
                except Exception:
                    pass

                # Clean up completed tokens. Two-tier eviction:
                #  1) Hard cap: keep only the 50 most-recent stopped tokens for history
                #     (count-based — protects against burst load).
                #  2) Time cap: drop any stopped token older than 24h regardless of count
                #     (time-based — protects against slow leak when a few stopped tokens
                #     just sit in the dict forever during a quiet day).
                stopped = [(a, t) for a, t in self._tracking.items() if t.stopped]
                if len(stopped) > 50:
                    oldest = sorted(stopped, key=lambda x: x[1].last_check)
                    for addr, _ in oldest[:-50]:
                        del self._tracking[addr]

                cutoff_24h = time.time() - 86400
                stale = [a for a, t in self._tracking.items() if t.stopped and t.last_check < cutoff_24h]
                for addr in stale:
                    del self._tracking[addr]

            except asyncio.CancelledError:
                break
            except Exception as e:
                log_error(f"[FollowUp] Loop error: {e}")

            await asyncio.sleep(5)  # Check every 5 seconds for tokens due

    def _fetch_mc(self, token_address: str) -> Optional[float]:
        """Fetch current MC from DexScreener. Runs in a thread."""
        try:
            from meridinate.services.dexscreener_service import get_dexscreener_service
            dex = get_dexscreener_service()
            snapshot = dex.get_token_snapshot(token_address)
            if snapshot:
                return snapshot.get("market_cap_usd") or 0
        except Exception:
            pass
        return None

    def _finalize_token(self, tracked: TrackedToken, mc_threshold: float):
        """Finalize a token's tracking — persist lifecycle data."""
        self._stats["total_completed"] += 1
        current_mc = tracked.trajectory[-1].mc if tracked.trajectory else 0

        log_info(
            f"[FollowUp] ✅ Finished tracking {tracked.token_name or tracked.token_address[:12]}... "
            f"peak=${tracked.peak_mc:,.0f} at {tracked.peak_minutes:.0f}min, "
            f"current=${current_mc:,.0f}, readings={len(tracked.trajectory)}, "
            f"reason={tracked.stop_reason}"
        )

        # Persist trajectory to webhook_detections
        self._persist_lifecycle(tracked)

        # Update webhook detection with final status
        self._update_webhook_detection(tracked)

    def _persist_lifecycle(self, tracked: TrackedToken):
        """Save the trajectory data to the database."""
        try:
            import sqlite3
            from meridinate.settings import DATABASE_FILE

            trajectory_json = json.dumps([asdict(r) for r in tracked.trajectory])

            conn = sqlite3.connect(DATABASE_FILE)
            conn.execute("""
                UPDATE webhook_detections SET
                    conviction_vs_outcome = ?
                WHERE token_address = ?
            """, (
                json.dumps({
                    "trajectory": [asdict(r) for r in tracked.trajectory],
                    "peak_mc": tracked.peak_mc,
                    "peak_mc_at": tracked.peak_mc_at,
                    "peak_minutes": tracked.peak_minutes,
                    "readings_count": len(tracked.trajectory),
                    "final_mc": tracked.trajectory[-1].mc if tracked.trajectory else 0,
                    "tracking_duration_minutes": (time.time() - tracked.start_time) / 60,
                    "stop_reason": tracked.stop_reason,
                }),
                tracked.token_address,
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            log_error(f"[FollowUp] Failed to persist lifecycle for {tracked.token_address[:12]}: {e}")

    def _update_webhook_detection(self, tracked: TrackedToken):
        """Update the webhook detection record with current status/score."""
        try:
            import sqlite3
            from meridinate.settings import DATABASE_FILE

            conn = sqlite3.connect(DATABASE_FILE)
            conn.execute("""
                UPDATE webhook_detections SET
                    conviction_score = ?,
                    status = ?
                WHERE token_address = ?
            """, (tracked.conviction_score, tracked.status, tracked.token_address))
            conn.commit()
            conn.close()
        except Exception as e:
            log_error(f"[FollowUp] Failed to update detection: {e}")

    def _fetch_token_name(self, token_address: str) -> Optional[str]:
        """Fetch token name if not already known."""
        try:
            from meridinate.services.pumpfun_service import get_pumpfun_token_data
            data = get_pumpfun_token_data(token_address)
            if data:
                return data.get("name")
        except Exception:
            pass
        return None


# Singleton
_tracker: Optional[FollowUpTracker] = None


def get_followup_tracker() -> FollowUpTracker:
    global _tracker
    if _tracker is None:
        _tracker = FollowUpTracker()
    return _tracker
