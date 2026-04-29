"""
PnL Backfill Manager

Runs the v2 PnL backfill as a managed background task inside the FastAPI process.
Tracks progress, supports start/stop, exposes state via API for frontend display.
"""

import asyncio
import time
from typing import Any, Dict, Optional

from meridinate.observability import log_error, log_info


class PnLBackfillManager:
    """Manages a single PnL backfill run with progress tracking."""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._state = {
            "status": "idle",  # idle, running, completed, stopped, error
            "wallets_total": 0,
            "wallets_processed": 0,
            "wallets_with_data": 0,
            "positions_updated": 0,
            "credits_used": 0,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "min_token_count": 5,
        }

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def state(self) -> dict:
        s = self._state.copy()
        if self._running and s["wallets_total"] > 0:
            s["progress_pct"] = round(s["wallets_processed"] / s["wallets_total"] * 100, 1)
            elapsed = time.time() - (s.get("_start_time") or time.time())
            if s["wallets_processed"] > 0:
                rate = s["wallets_processed"] / elapsed
                remaining = (s["wallets_total"] - s["wallets_processed"]) / rate
                s["estimated_remaining_seconds"] = round(remaining)
            else:
                s["estimated_remaining_seconds"] = None
        else:
            s["progress_pct"] = 100 if s["status"] == "completed" else 0
            s["estimated_remaining_seconds"] = None
        s.pop("_start_time", None)
        return s

    async def start(self, min_token_count: int = 5):
        """Start the backfill in the background."""
        if self._running:
            return {"status": "already_running", **self.state}

        self._running = True
        self._state = {
            "status": "running",
            "wallets_total": 0,
            "wallets_processed": 0,
            "wallets_with_data": 0,
            "positions_updated": 0,
            "credits_used": 0,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "completed_at": None,
            "error": None,
            "min_token_count": min_token_count,
            "_start_time": time.time(),
        }
        self._task = asyncio.create_task(self._run_backfill(min_token_count))
        return {"status": "started", **self.state}

    async def stop(self):
        """Stop the running backfill."""
        if not self._running:
            return {"status": "not_running"}
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._state["status"] = "stopped"
        self._state["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        log_info(f"[PnL Backfill] Stopped at {self._state['wallets_processed']}/{self._state['wallets_total']} wallets")
        return {"status": "stopped", **self.state}

    async def _run_backfill(self, min_token_count: int):
        """The actual backfill loop."""
        from meridinate import analyzed_tokens_db as db
        from meridinate.services.pnl_calculator_v2 import compute_and_store_wallet_pnl_v2
        from meridinate.settings import HELIUS_API_KEY
        from meridinate.credit_tracker import get_credit_tracker

        try:
            # Get wallets needing PnL, filtered by token count
            with db.get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT ebw.wallet_address, COUNT(DISTINCT ebw.token_id) as token_count
                    FROM early_buyer_wallets ebw
                    JOIN analyzed_tokens t ON t.id = ebw.token_id AND (t.deleted_at IS NULL OR t.deleted_at = '')
                    LEFT JOIN mtew_token_positions mtp
                        ON mtp.wallet_address = ebw.wallet_address
                        AND mtp.token_id = ebw.token_id
                        AND mtp.pnl_source = 'helius_enhanced'
                        AND mtp.total_bought_usd > 1
                    GROUP BY ebw.wallet_address
                    HAVING token_count >= ?
                    AND COUNT(CASE WHEN mtp.id IS NOT NULL THEN 1 END) < token_count
                    ORDER BY token_count DESC
                """, (min_token_count,))
                wallets = [(r[0], r[1]) for r in cursor.fetchall()]

            self._state["wallets_total"] = len(wallets)
            log_info(f"[PnL Backfill] Starting: {len(wallets)} wallets with {min_token_count}+ tokens")

            for wallet_addr, token_count in wallets:
                if not self._running:
                    break

                try:
                    result = await asyncio.to_thread(
                        compute_and_store_wallet_pnl_v2, wallet_addr, HELIUS_API_KEY
                    )
                    self._state["wallets_processed"] += 1
                    self._state["credits_used"] += result.get("credits_used", 0)
                    updated = result.get("positions_updated", 0)
                    self._state["positions_updated"] += updated
                    if updated > 0:
                        self._state["wallets_with_data"] += 1

                except Exception as e:
                    self._state["wallets_processed"] += 1
                    log_error(f"[PnL Backfill] Failed for {wallet_addr[:12]}...: {e}")

                # Brief yield to not block the event loop
                await asyncio.sleep(0.1)

            if self._running:
                self._state["status"] = "completed"
            self._state["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")

            get_credit_tracker().record_operation(
                operation="pnl_v2_backfill", label="PnL v2 Backfill",
                credits=self._state["credits_used"],
                call_count=self._state["wallets_processed"],
                context={
                    "positions": self._state["positions_updated"],
                    "wallets_with_data": self._state["wallets_with_data"],
                    "min_token_count": min_token_count,
                },
            )

            log_info(
                f"[PnL Backfill] {self._state['status']}: "
                f"{self._state['wallets_processed']}/{self._state['wallets_total']} wallets, "
                f"{self._state['positions_updated']} positions, "
                f"{self._state['wallets_with_data']} with data, "
                f"{self._state['credits_used']} credits"
            )

        except asyncio.CancelledError:
            self._state["status"] = "stopped"
        except Exception as e:
            self._state["status"] = "error"
            self._state["error"] = str(e)
            log_error(f"[PnL Backfill] Error: {e}")
        finally:
            self._running = False


# Singleton
_manager: Optional[PnLBackfillManager] = None


def get_backfill_manager() -> PnLBackfillManager:
    global _manager
    if _manager is None:
        _manager = PnLBackfillManager()
    return _manager
