"""
Wallet Shadow — Real-Time Bot Tracking via Helius Enhanced WebSocket

Subscribes to transactions involving tracked wallets and records every trade
in real-time. Zero Helius credits (WebSocket is free). Captures trades that
historical probes miss due to closed token accounts.

Designed for tracking multiple wallets simultaneously. Each wallet's
transactions are parsed for buy/sell direction, SOL amount, token amount,
tip infrastructure, and timing relative to token creation.

Uses a separate WebSocket connection from the RTTF token detection listener
to avoid interference.
"""

import asyncio
import json
import sqlite3
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field

from meridinate import analyzed_tokens_db as db
from meridinate.observability import log_error, log_info
from meridinate.settings import HELIUS_API_KEY

CHICAGO_TZ = ZoneInfo("America/Chicago")
PING_INTERVAL = 30
DUST_THRESHOLD_SOL = 0.005
MAX_FEED_SIZE = 200

# System addresses to exclude from signal wallet analysis
# These are protocol infrastructure, not real traders
EXCLUDED_SIGNAL_WALLETS = {
    # PumpFun
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",   # PumpFun program
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",    # PumpSwap AMM
    "Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjQ7GWFphsXY",  # PumpFun fee account
    "CebN5WGQ4jvEPvsVU4EoHEpgULkN3zUrykTrEHN4nFZh",  # PumpFun authority
    "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg",  # PumpFun global config
    # Solana system
    "11111111111111111111111111111111",                  # System Program
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",    # Token Program
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",   # Associated Token Program
    "So11111111111111111111111111111111111111111",       # Wrapped SOL
    "ComputeBudget111111111111111111111111111111",       # Compute Budget
    # Raydium
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Raydium AMM
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",  # Raydium authority
    # Jupiter
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",   # Jupiter v6
    # Meteora
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",   # Meteora DLMM
}


@dataclass
class ShadowTrade:
    """A trade captured in real-time from a tracked wallet."""
    wallet_address: str
    token_address: str
    token_name: Optional[str]
    direction: str  # buy / sell
    sol_amount: float
    token_amount: float
    timestamp: str
    timestamp_unix: int
    signature: str
    block_slot: Optional[int]
    tip_type: Optional[str]
    entry_seconds_after_creation: Optional[float] = None

    def to_dict(self):
        return {
            "wallet_address": self.wallet_address,
            "token_address": self.token_address,
            "token_name": self.token_name,
            "direction": self.direction,
            "sol_amount": self.sol_amount,
            "token_amount": self.token_amount,
            "timestamp": self.timestamp,
            "timestamp_unix": self.timestamp_unix,
            "signature": self.signature,
            "block_slot": self.block_slot,
            "tip_type": self.tip_type,
            "entry_seconds_after_creation": self.entry_seconds_after_creation,
        }


def _ensure_tables():
    with db.get_db_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS wallet_shadow_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address TEXT NOT NULL UNIQUE,
                label TEXT,
                added_at TEXT,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS wallet_shadow_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address TEXT NOT NULL,
                token_address TEXT NOT NULL,
                token_name TEXT,
                direction TEXT NOT NULL,
                sol_amount REAL NOT NULL DEFAULT 0,
                token_amount REAL NOT NULL DEFAULT 0,
                timestamp TEXT,
                timestamp_unix INTEGER,
                signature TEXT NOT NULL,
                block_slot INTEGER,
                tip_type TEXT,
                entry_seconds_after_creation REAL,
                captured_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_wst_wallet ON wallet_shadow_trades(wallet_address);
            CREATE INDEX IF NOT EXISTS idx_wst_token ON wallet_shadow_trades(token_address);
            CREATE INDEX IF NOT EXISTS idx_wst_time ON wallet_shadow_trades(timestamp_unix);

            CREATE TABLE IF NOT EXISTS wallet_shadow_preceding_buyers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER,
                tracked_wallet TEXT NOT NULL,
                token_address TEXT NOT NULL,
                preceding_wallet TEXT NOT NULL,
                preceding_sol_amount REAL,
                preceding_timestamp_unix INTEGER,
                seconds_before_tracked REAL,
                captured_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS wallet_shadow_convergences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_address TEXT NOT NULL,
                token_name TEXT,
                wallets_json TEXT NOT NULL,
                wallet_count INTEGER NOT NULL,
                first_entry_unix INTEGER,
                last_entry_unix INTEGER,
                spread_seconds REAL,
                captured_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_wspb_tracked ON wallet_shadow_preceding_buyers(tracked_wallet);
            CREATE INDEX IF NOT EXISTS idx_wspb_preceding ON wallet_shadow_preceding_buyers(preceding_wallet);
            CREATE INDEX IF NOT EXISTS idx_wsc_token ON wallet_shadow_convergences(token_address);
        """)


def get_tracked_wallets() -> List[Dict]:
    """Get all tracked wallet targets."""
    _ensure_tables()
    with db.get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM wallet_shadow_targets ORDER BY added_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_active_wallet_addresses() -> Set[str]:
    """Get addresses of actively tracked wallets."""
    _ensure_tables()
    with db.get_db_connection() as conn:
        rows = conn.execute(
            "SELECT wallet_address FROM wallet_shadow_targets WHERE active = 1"
        ).fetchall()
        return {r[0] for r in rows}


def add_tracked_wallet(wallet_address: str, label: str = "") -> Dict:
    """Add a wallet to the tracking list."""
    _ensure_tables()
    now = datetime.now(CHICAGO_TZ).strftime("%b %d, %Y %I:%M %p %Z")
    with db.get_db_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO wallet_shadow_targets (wallet_address, label, added_at, active) VALUES (?, ?, ?, 1)",
                (wallet_address, label, now),
            )
            log_info(f"[WalletShadow] Added tracking target: {wallet_address[:16]}... ({label})")
            return {"success": True, "message": f"Now tracking {wallet_address}"}
        except sqlite3.IntegrityError:
            # Already exists — reactivate
            conn.execute(
                "UPDATE wallet_shadow_targets SET active = 1, label = ? WHERE wallet_address = ?",
                (label or None, wallet_address),
            )
            return {"success": True, "message": f"Reactivated tracking for {wallet_address}"}


def remove_tracked_wallet(wallet_address: str) -> Dict:
    """Deactivate tracking for a wallet (keeps history)."""
    _ensure_tables()
    with db.get_db_connection() as conn:
        conn.execute(
            "UPDATE wallet_shadow_targets SET active = 0 WHERE wallet_address = ?",
            (wallet_address,),
        )
    log_info(f"[WalletShadow] Stopped tracking: {wallet_address[:16]}...")
    return {"success": True, "message": f"Stopped tracking {wallet_address}"}


def _store_trade(trade: ShadowTrade) -> Optional[int]:
    """Persist a captured trade to the database. Returns trade ID or None if deduped."""
    with db.get_db_connection() as conn:
        # Dedup: skip if signature already recorded for this wallet
        existing = conn.execute(
            "SELECT 1 FROM wallet_shadow_trades WHERE wallet_address = ? AND signature = ? LIMIT 1",
            (trade.wallet_address, trade.signature),
        ).fetchone()
        if existing:
            return None

        cur = conn.execute("""
            INSERT INTO wallet_shadow_trades
            (wallet_address, token_address, token_name, direction, sol_amount, token_amount,
             timestamp, timestamp_unix, signature, block_slot, tip_type,
             entry_seconds_after_creation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade.wallet_address, trade.token_address, trade.token_name,
            trade.direction, trade.sol_amount, trade.token_amount,
            trade.timestamp, trade.timestamp_unix, trade.signature,
            trade.block_slot, trade.tip_type, trade.entry_seconds_after_creation,
        ))
        return cur.lastrowid


def _lookup_token_name(token_address: str) -> Optional[str]:
    """Look up token name from Meridinate's database."""
    try:
        with db.get_db_connection() as conn:
            row = conn.execute(
                "SELECT token_name FROM analyzed_tokens WHERE token_address = ? LIMIT 1",
                (token_address,),
            ).fetchone()
            return row[0] if row else None
    except Exception:
        return None


def _get_token_birth(token_address: str) -> Optional[int]:
    """Get token creation timestamp (Unix) if known."""
    # Try RTTF in-memory feed first (most accurate for recent tokens)
    try:
        from meridinate.services.realtime_listener import get_realtime_listener
        listener = get_realtime_listener()
        for detection in listener.get_feed():
            if detection.get("token_address") == token_address:
                det_at = detection.get("detected_at")
                if det_at:
                    ts = str(det_at)
                    if ts.isdigit():
                        return int(ts)
                    try:
                        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
                    except (ValueError, TypeError):
                        pass
    except Exception:
        pass

    try:
        with db.get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            # Try webhook_detections DB
            row = conn.execute(
                "SELECT detected_at FROM webhook_detections WHERE token_address = ? LIMIT 1",
                (token_address,),
            ).fetchone()
            if row and row["detected_at"]:
                ts = str(row["detected_at"])
                if ts.isdigit():
                    return int(ts)
                try:
                    return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
                except (ValueError, TypeError):
                    pass

            # Try first_buy_timestamp
            row = conn.execute(
                "SELECT first_buy_timestamp FROM analyzed_tokens WHERE token_address = ? LIMIT 1",
                (token_address,),
            ).fetchone()
            if row and row["first_buy_timestamp"]:
                ts = str(row["first_buy_timestamp"])
                if ts.isdigit():
                    return int(ts)
                try:
                    return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    return None


def _capture_preceding_buyers(
    trade_id: int,
    tracked_wallet: str,
    token_address: str,
    entry_timestamp_unix: int,
    max_sigs: int = 50,
):
    """
    After a tracked wallet BUYs a token, find who bought before it.
    Runs in a background thread to avoid blocking the WebSocket loop.

    Costs: ~1 + N credits (N = transactions to parse, typically 10-30)
    """
    try:
        from meridinate.helius_api import HeliusAPI
        from meridinate.settings import HELIUS_API_KEY
        helius = HeliusAPI(HELIUS_API_KEY)

        # Get recent signatures on the token mint
        sigs = helius._rpc_call(
            "getSignaturesForAddress",
            [token_address, {"limit": max_sigs}]
        ) or []

        preceding = []
        tracked_addresses = get_active_wallet_addresses()

        for sig_obj in sigs:
            sig = sig_obj.get("signature")
            if not sig:
                continue

            try:
                tx_data = helius._rpc_call(
                    "getTransaction",
                    [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
                )
                if not tx_data or not isinstance(tx_data, dict):
                    continue

                meta = tx_data.get("meta", {})
                if meta.get("err"):
                    continue

                block_time = tx_data.get("blockTime")
                if not block_time or block_time >= entry_timestamp_unix:
                    continue  # Only want transactions BEFORE our entry

                pre_balances = meta.get("preTokenBalances", [])
                post_balances = meta.get("postTokenBalances", [])

                # Identify bonding curve accounts (hold massive token supply, unique per token)
                bonding_curve_addrs = set()
                for b in pre_balances:
                    if b.get("mint") == token_address:
                        amt = float(b.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                        if amt > 100_000_000:  # >100M tokens = likely bonding curve
                            if b.get("owner"):
                                bonding_curve_addrs.add(b["owner"])

                # Find wallets that gained tokens (buyers)
                for b in post_balances:
                    owner = b.get("owner")
                    mint = b.get("mint")
                    if mint != token_address or not owner:
                        continue
                    if owner == tracked_wallet:
                        continue  # Skip our own wallet
                    if owner in tracked_addresses:
                        continue  # Skip other tracked wallets (handled by convergence)
                    if owner in EXCLUDED_SIGNAL_WALLETS:
                        continue  # Skip known system/protocol addresses
                    if owner in bonding_curve_addrs:
                        continue  # Skip bonding curve accounts

                    post_amt = float(b.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                    pre_amt = 0
                    for pb in pre_balances:
                        if pb.get("owner") == owner and pb.get("mint") == token_address:
                            pre_amt = float(pb.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)

                    if post_amt > pre_amt + 0.001:
                        # This wallet bought before us
                        # Estimate SOL spent from balance changes
                        pre_sol_list = meta.get("preBalances", [])
                        post_sol_list = meta.get("postBalances", [])
                        account_keys = tx_data.get("transaction", {}).get("message", {}).get("accountKeys", [])
                        key_list = [(ak.get("pubkey", ak) if isinstance(ak, dict) else ak) for ak in account_keys]

                        sol_spent = 0
                        if owner in key_list:
                            idx = key_list.index(owner)
                            if idx < len(pre_sol_list) and idx < len(post_sol_list):
                                sol_spent = abs(pre_sol_list[idx] - post_sol_list[idx]) / 1e9

                        preceding.append({
                            "wallet": owner,
                            "sol_amount": round(sol_spent, 6),
                            "timestamp_unix": block_time,
                            "seconds_before": entry_timestamp_unix - block_time,
                        })

            except Exception:
                continue

        # Store preceding buyers
        if preceding:
            with db.get_db_connection() as conn:
                for p in preceding:
                    conn.execute("""
                        INSERT INTO wallet_shadow_preceding_buyers
                        (trade_id, tracked_wallet, token_address, preceding_wallet,
                         preceding_sol_amount, preceding_timestamp_unix, seconds_before_tracked)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        trade_id, tracked_wallet, token_address,
                        p["wallet"], p["sol_amount"], p["timestamp_unix"], p["seconds_before"],
                    ))

            log_info(
                f"[WalletShadow] Found {len(preceding)} preceding buyers for "
                f"{tracked_wallet[:12]}... on {token_address[:12]}..."
            )

    except Exception as e:
        log_error(f"[WalletShadow] Preceding buyer capture failed: {e}")


def _check_convergence(token_address: str, token_name: Optional[str]):
    """
    Check if 2+ tracked wallets have entered the same token.
    Called after every BUY to detect cross-bot convergence.
    """
    try:
        tracked_addresses = get_active_wallet_addresses()
        with db.get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT wallet_address, MIN(timestamp_unix) as first_entry, MAX(timestamp_unix) as last_entry,
                       COUNT(*) as buy_count, ROUND(SUM(sol_amount), 4) as total_sol
                FROM wallet_shadow_trades
                WHERE token_address = ? AND direction = 'buy' AND wallet_address IN ({})
                GROUP BY wallet_address
            """.format(",".join("?" for _ in tracked_addresses)),
                (token_address, *tracked_addresses),
            ).fetchall()

            if len(rows) < 2:
                return  # No convergence

            wallets_data = []
            first_entry = None
            last_entry = None
            for r in rows:
                d = dict(r)
                label_row = conn.execute(
                    "SELECT label FROM wallet_shadow_targets WHERE wallet_address = ?",
                    (d["wallet_address"],),
                ).fetchone()
                d["label"] = label_row[0] if label_row else None
                wallets_data.append(d)
                ts = d["first_entry"]
                if ts:
                    if first_entry is None or ts < first_entry:
                        first_entry = ts
                    if last_entry is None or ts > last_entry:
                        last_entry = ts

            spread = (last_entry - first_entry) if first_entry and last_entry else 0

            # Check if we already logged this convergence
            existing = conn.execute(
                "SELECT id FROM wallet_shadow_convergences WHERE token_address = ? AND wallet_count = ?",
                (token_address, len(rows)),
            ).fetchone()

            if not existing:
                conn.execute("""
                    INSERT INTO wallet_shadow_convergences
                    (token_address, token_name, wallets_json, wallet_count,
                     first_entry_unix, last_entry_unix, spread_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    token_address, token_name, json.dumps(wallets_data, default=str),
                    len(rows), first_entry, last_entry, spread,
                ))

                wallet_labels = [w.get("label") or w["wallet_address"][:10] for w in wallets_data]
                log_info(
                    f"[WalletShadow] CONVERGENCE: {len(rows)} tracked wallets on "
                    f"{token_name or token_address[:12]}... — {', '.join(wallet_labels)} "
                    f"(spread: {spread:.0f}s)"
                )
            else:
                # Update count if more wallets joined
                conn.execute("""
                    UPDATE wallet_shadow_convergences SET
                        wallets_json = ?, wallet_count = ?, last_entry_unix = ?, spread_seconds = ?
                    WHERE token_address = ? AND id = ?
                """, (
                    json.dumps(wallets_data, default=str), len(rows), last_entry, spread,
                    token_address, existing[0],
                ))

    except Exception as e:
        log_error(f"[WalletShadow] Convergence check failed: {e}")


class WalletShadowListener:
    """
    Manages a Helius Enhanced WebSocket connection for tracking
    multiple wallet addresses in real-time.

    Separate from the RTTF listener to avoid interference.
    Supports dynamic add/remove of tracked wallets with
    automatic resubscription.
    """

    def __init__(self):
        self.ws_url = f"wss://atlas-mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
        self._running = False
        self._ws = None
        self._listen_task = None
        self._subscription_id = None
        self._tracked_addresses: Set[str] = set()
        self._on_trade_callback: Optional[callable] = None

        # Live feed (in-memory ring buffer for UI)
        self._feed: List[Dict] = []

        # Stats
        self._stats = {
            "connected": False,
            "trades_captured": 0,
            "wallets_tracked": 0,
            "last_trade_at": None,
            "reconnect_count": 0,
            "started_at": None,
        }

    def set_on_trade(self, callback):
        """Set callback fired on each captured trade."""
        self._on_trade_callback = callback

    def get_feed(self, limit: int = 50, wallet: str = None) -> List[Dict]:
        """Get recent trades from in-memory feed."""
        if wallet:
            return [t for t in self._feed if t.get("wallet_address") == wallet][-limit:]
        return self._feed[-limit:]

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "wallets_tracked": len(self._tracked_addresses),
            "tracked_wallets": list(self._tracked_addresses),
            "feed_size": len(self._feed),
        }

    async def start(self):
        """Start the shadow listener."""
        if self._running:
            return

        # Load tracked wallets from DB
        self._tracked_addresses = get_active_wallet_addresses()
        if not self._tracked_addresses:
            log_info("[WalletShadow] No wallets to track. Add wallets first.")
            return

        self._running = True
        self._stats["started_at"] = datetime.now(CHICAGO_TZ).strftime("%b %d, %Y %I:%M %p %Z")
        self._listen_task = asyncio.create_task(self._listen_loop())
        log_info(f"[WalletShadow] Started — tracking {len(self._tracked_addresses)} wallets")

    async def stop(self):
        """Stop the shadow listener."""
        self._running = False
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        self._stats["connected"] = False
        log_info("[WalletShadow] Stopped")

    async def refresh_wallets(self):
        """Reload tracked wallets from DB and resubscribe if changed."""
        new_addrs = get_active_wallet_addresses()
        if new_addrs != self._tracked_addresses:
            old_count = len(self._tracked_addresses)
            self._tracked_addresses = new_addrs
            self._stats["wallets_tracked"] = len(new_addrs)
            log_info(f"[WalletShadow] Wallet list updated: {old_count} → {len(new_addrs)}")

            # Resubscribe with new wallet list
            if self._ws and not self._ws.closed:
                await self._subscribe(self._ws)

    async def _listen_loop(self):
        """Main WebSocket loop with reconnection."""
        import websockets

        while self._running:
            try:
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=PING_INTERVAL,
                    ping_timeout=10,
                    max_size=10 * 1024 * 1024,
                ) as ws:
                    self._ws = ws
                    self._stats["connected"] = True
                    log_info("[WalletShadow] WebSocket connected")

                    await self._subscribe(ws)

                    async for message in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(message)
                            await self._handle_message(data)
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            log_error(f"[WalletShadow] Message error: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._stats["connected"] = False
                self._stats["reconnect_count"] += 1
                log_error(f"[WalletShadow] WebSocket error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _subscribe(self, ws):
        """Subscribe to transactions involving tracked wallets."""
        if not self._tracked_addresses:
            return

        # Helius Enhanced WebSocket: transactionSubscribe with accountInclude
        subscribe_msg = {
            "jsonrpc": "2.0",
            "id": 420,
            "method": "transactionSubscribe",
            "params": [
                {
                    "vote": False,
                    "failed": False,
                    "accountInclude": list(self._tracked_addresses),
                },
                {
                    "commitment": "confirmed",
                    "encoding": "jsonParsed",
                    "transactionDetails": "full",
                    "maxSupportedTransactionVersion": 0,
                }
            ]
        }
        await ws.send(json.dumps(subscribe_msg))
        log_info(f"[WalletShadow] Subscribed to {len(self._tracked_addresses)} wallet(s)")

    async def _handle_message(self, data: dict):
        """Process incoming transaction notifications."""
        if "result" in data and "id" in data:
            self._subscription_id = data["result"]
            log_info(f"[WalletShadow] Subscription confirmed: {self._subscription_id}")
            return

        if data.get("method") != "transactionNotification":
            return

        params = data.get("params", {})
        result = params.get("result", {})
        tx = result.get("transaction", {})
        signature = result.get("signature", "")
        slot = result.get("slot")

        if not tx:
            return

        meta = tx.get("meta", {})
        if meta.get("err"):
            return  # Skip failed transactions

        # Get timestamp
        block_time = tx.get("blockTime") or result.get("blockTime")
        timestamp_unix = block_time if block_time else int(time.time())
        timestamp_iso = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc).isoformat()

        # Parse pre/post token balances
        pre_balances = meta.get("preTokenBalances", [])
        post_balances = meta.get("postTokenBalances", [])
        pre_sol = meta.get("preBalances", [])
        post_sol = meta.get("postBalances", [])

        # Get account keys to map indices to addresses
        account_keys = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
        key_list = []
        for ak in account_keys:
            if isinstance(ak, dict):
                key_list.append(ak.get("pubkey", ""))
            else:
                key_list.append(str(ak))

        # Detect tip infrastructure — check if any tip address RECEIVED SOL
        tip_type = None
        try:
            from meridinate.services.tip_detector import NOZOMI_TIP_ADDRESSES, JITO_TIP_ADDRESSES
            if pre_sol and post_sol:
                for i, key in enumerate(key_list):
                    if i < len(pre_sol) and i < len(post_sol):
                        sol_received = (post_sol[i] - pre_sol[i]) / 1e9
                        if sol_received > 0.00001:  # Received SOL = tip payment
                            if key in NOZOMI_TIP_ADDRESSES:
                                tip_type = "nozomi"
                                break
                            if key in JITO_TIP_ADDRESSES:
                                tip_type = "jito"
                                break
        except Exception:
            pass

        # Find trades for each tracked wallet
        for wallet_addr in self._tracked_addresses:
            # Find wallet's index in account keys
            wallet_idx = None
            for idx, key in enumerate(key_list):
                if key == wallet_addr:
                    wallet_idx = idx
                    break

            if wallet_idx is None:
                continue

            # SOL change for this wallet
            sol_change = 0
            if wallet_idx < len(pre_sol) and wallet_idx < len(post_sol):
                sol_change = (post_sol[wallet_idx] - pre_sol[wallet_idx]) / 1e9

            # Find token balance changes for this wallet
            wallet_mints = set()
            for b in pre_balances + post_balances:
                if b.get("owner") == wallet_addr and b.get("mint"):
                    wallet_mints.add(b["mint"])

            for mint in wallet_mints:
                pre_amt = 0
                post_amt = 0
                for b in pre_balances:
                    if b.get("owner") == wallet_addr and b.get("mint") == mint:
                        pre_amt = float(b.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                for b in post_balances:
                    if b.get("owner") == wallet_addr and b.get("mint") == mint:
                        post_amt = float(b.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)

                token_delta = post_amt - pre_amt
                if abs(token_delta) < 0.001:
                    continue

                is_buy = token_delta > 0
                sol_amount = abs(sol_change)
                if sol_amount < DUST_THRESHOLD_SOL:
                    continue

                # Look up token name and birth time
                token_name = _lookup_token_name(mint)
                entry_secs = None
                if is_buy:
                    birth_ts = _get_token_birth(mint)
                    if birth_ts and timestamp_unix:
                        delta = timestamp_unix - birth_ts
                        if delta >= 0:
                            entry_secs = round(delta, 1)

                trade = ShadowTrade(
                    wallet_address=wallet_addr,
                    token_address=mint,
                    token_name=token_name,
                    direction="buy" if is_buy else "sell",
                    sol_amount=round(sol_amount, 9),
                    token_amount=round(abs(token_delta), 6),
                    timestamp=timestamp_iso,
                    timestamp_unix=timestamp_unix,
                    signature=signature,
                    block_slot=slot,
                    tip_type=tip_type,
                    entry_seconds_after_creation=entry_secs,
                )

                # Store to DB
                trade_id = _store_trade(trade)
                if trade_id is None:
                    continue  # Deduped

                # On BUY: capture preceding buyers + check convergence (background thread)
                if trade.direction == "buy":
                    import threading
                    threading.Thread(
                        target=_capture_preceding_buyers,
                        args=(trade_id, wallet_addr, mint, timestamp_unix),
                        daemon=True,
                    ).start()
                    _check_convergence(mint, token_name)

                # Add to in-memory feed
                trade_dict = trade.to_dict()
                self._feed.append(trade_dict)
                if len(self._feed) > MAX_FEED_SIZE:
                    self._feed = self._feed[-MAX_FEED_SIZE:]

                self._stats["trades_captured"] += 1
                self._stats["last_trade_at"] = datetime.now(CHICAGO_TZ).strftime("%I:%M:%S %p")

                # Fire callback
                if self._on_trade_callback:
                    try:
                        self._on_trade_callback(trade_dict)
                    except Exception:
                        pass

                log_info(
                    f"[WalletShadow] {wallet_addr[:12]}... {'BOUGHT' if is_buy else 'SOLD'} "
                    f"{sol_amount:.4f} SOL of {token_name or mint[:12]}... "
                    f"(entry: {entry_secs}s)" if entry_secs else
                    f"[WalletShadow] {wallet_addr[:12]}... {'BOUGHT' if is_buy else 'SOLD'} "
                    f"{sol_amount:.4f} SOL of {token_name or mint[:12]}..."
                )


# Singleton
_shadow_listener: Optional[WalletShadowListener] = None


def get_shadow_listener() -> WalletShadowListener:
    global _shadow_listener
    if _shadow_listener is None:
        _shadow_listener = WalletShadowListener()
    return _shadow_listener
