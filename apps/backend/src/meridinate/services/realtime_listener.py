"""
Real-Time Token Detection via Helius Enhanced WebSocket

Connects to Helius's enhanced WebSocket and subscribes to PumpFun program
transactions. Filters for token creation events and computes a conviction
score based on deployer history, safety checks, and early buyer signals.

Usage:
    from meridinate.services.realtime_listener import get_realtime_listener
    listener = get_realtime_listener()
    await listener.start()   # begins listening
    await listener.stop()    # stops listening
    listener.get_feed()      # returns recent detected tokens
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field, asdict

from meridinate.observability import log_error, log_info
from meridinate.settings import HELIUS_API_KEY

# PumpFun program addresses
PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPFUN_AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"

# Maximum feed items to keep in memory
MAX_FEED_SIZE = 100

# Ping interval to keep WebSocket alive (Helius times out after 10 min)
PING_INTERVAL = 30  # seconds


@dataclass
class DetectedToken:
    """A token detected via real-time WebSocket."""
    token_address: str
    deployer_address: Optional[str]
    detected_at: str
    signature: str
    initial_sol: float = 0.0
    # Conviction scoring
    conviction_score: int = 0
    deployer_score: int = 0
    safety_score: int = 0
    social_proof_score: int = 0
    # Deployer info
    deployer_token_count: int = 0
    deployer_win_rate: Optional[float] = None
    deployer_tags: List[str] = field(default_factory=list)
    # Safety info
    mint_authority_revoked: Optional[bool] = None
    freeze_authority_active: Optional[bool] = None
    deployer_sol_balance: Optional[float] = None
    deployer_funded_by: Optional[str] = None
    deployer_funding_hops: int = 0
    # Social proof (fills in over time via watch window)
    smart_wallets_buying: int = 0
    smart_wallet_names: List[str] = field(default_factory=list)
    fresh_buyer_count: int = 0
    total_buyers: int = 0
    # Crime coin detection (filled after 60-second watch window)
    crime_risk_score: int = 0
    buys_in_first_3_blocks: int = 0
    fresh_buyer_pct: float = 0.0
    buyers_sharing_funder: int = 0
    deployer_linked_to_buyer: bool = False
    buy_amount_uniformity: float = 0.0  # std_dev / mean — low = suspicious
    mc_at_30s: float = 0.0
    unique_buyers_30s: int = 0
    watch_window_complete: bool = False
    # Status
    status: str = "watching"  # "high_conviction", "watching", "weak", "rejected"
    rejection_reason: Optional[str] = None
    # Token metadata (filled in after PumpFun API call)
    token_name: Optional[str] = None
    token_symbol: Optional[str] = None

    def to_dict(self):
        return asdict(self)


class RealtimeListener:
    """
    Manages the Helius Enhanced WebSocket connection for real-time
    PumpFun token creation detection.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.ws_url = f"wss://mainnet.helius-rpc.com/?api-key={api_key}"
        self._ws = None
        self._running = False
        self._feed: List[DetectedToken] = []
        self._task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._subscription_id: Optional[int] = None
        self._on_token_detected: Optional[Callable] = None
        # Watch window: tracks tokens being monitored for 60 seconds post-creation
        # Key: token_address, Value: {"detected": DetectedToken, "buys": [...], "start_time": float, "creation_block": int}
        self._watching: Dict[str, Dict] = {}
        self._stats = {
            "connected": False,
            "total_detected": 0,
            "total_rejected": 0,
            "total_high_conviction": 0,
            "total_crime_coins": 0,
            "session_start": None,
            "last_event_at": None,
            "reconnect_count": 0,
        }

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stats(self) -> dict:
        return {**self._stats, "feed_size": len(self._feed)}

    def get_feed(self, limit: int = 50) -> List[dict]:
        """Get recent detected tokens, newest first."""
        return [t.to_dict() for t in self._feed[:limit]]

    def set_callback(self, callback: Callable):
        """Set a callback function that fires when a new token is detected."""
        self._on_token_detected = callback

    async def start(self):
        """Start the WebSocket listener."""
        if self._running:
            log_info("[RealtimeListener] Already running")
            return

        self._running = True
        self._stats["session_start"] = datetime.now(timezone.utc).isoformat()
        self._task = asyncio.create_task(self._listen_loop())

        # Auto-start follow-up tracker
        try:
            from meridinate.services.followup_tracker import get_followup_tracker
            tracker = get_followup_tracker()
            if not tracker.is_running:
                await tracker.start()
        except Exception as e:
            log_error(f"[RealtimeListener] Follow-up tracker start failed: {e}")

        log_info("[RealtimeListener] Started")

    async def stop(self):
        """Stop the WebSocket listener."""
        self._running = False
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
        if self._ws:
            await self._ws.close()
        if self._task and not self._task.done():
            self._task.cancel()
        self._stats["connected"] = False
        log_info("[RealtimeListener] Stopped")

    async def _listen_loop(self):
        """Main loop with reconnection logic."""
        import websockets

        while self._running:
            try:
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=PING_INTERVAL,
                    ping_timeout=10,
                    max_size=10 * 1024 * 1024,  # 10MB max message
                ) as ws:
                    self._ws = ws
                    self._stats["connected"] = True
                    log_info("[RealtimeListener] WebSocket connected")

                    # Subscribe to PumpFun program transactions
                    await self._subscribe(ws)

                    # Listen for messages
                    async for message in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(message)
                            await self._handle_message(data)
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            log_error(f"[RealtimeListener] Message handling error: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._stats["connected"] = False
                self._stats["reconnect_count"] += 1
                log_error(f"[RealtimeListener] WebSocket error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _subscribe(self, ws):
        """Subscribe to PumpFun token creation transactions."""
        subscribe_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "transactionSubscribe",
            "params": [
                {
                    "vote": False,
                    "failed": False,
                    "accountInclude": [PUMPFUN_PROGRAM, PUMPFUN_AMM],
                    "accountExclude": [],
                    "accountRequired": [],
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
        log_info("[RealtimeListener] Subscribed to PumpFun transactions")

    async def _handle_message(self, data: dict):
        """Process incoming WebSocket messages."""
        # Subscription confirmation
        if "result" in data and "id" in data:
            self._subscription_id = data["result"]
            log_info(f"[RealtimeListener] Subscription confirmed: {self._subscription_id}")
            return

        # Transaction notification
        if "method" not in data or data["method"] != "transactionNotification":
            return

        params = data.get("params", {})
        result = params.get("result", {})
        tx = result.get("transaction", {})

        if not tx:
            return

        # Check watch windows: collect buy data for tokens being monitored
        await self._collect_watch_data(tx)

        # Check expired watch windows
        await self._process_expired_watches()

        # Check if this is a token creation transaction
        token_info = self._extract_token_creation(tx)
        if not token_info:
            return  # Not a creation event

        token_address = token_info["token_address"]
        deployer_address = token_info["deployer_address"]
        initial_sol = token_info.get("initial_sol", 0)
        signature = token_info.get("signature", "")
        creation_slot = token_info.get("slot", 0)

        self._stats["last_event_at"] = datetime.now(timezone.utc).isoformat()

        # Check if we already detected this token
        if any(t.token_address == token_address for t in self._feed):
            return

        # Create detection entry
        detected = DetectedToken(
            token_address=token_address,
            deployer_address=deployer_address,
            detected_at=datetime.now(timezone.utc).isoformat(),
            signature=signature,
            initial_sol=initial_sol,
        )

        # Compute conviction score (enriches with DB data, no API calls)
        await self._compute_conviction(detected)

        # Update stats (count ALL detections)
        self._stats["total_detected"] += 1
        if detected.status == "high_conviction":
            self._stats["total_high_conviction"] += 1
        elif detected.status == "rejected":
            self._stats["total_rejected"] += 1

        # Only add to visible feed if noteworthy:
        # - Known deployer (we have history on them)
        # - High conviction (70+) or explicit rejection (known rugger)
        # - Not just a random unknown token with a neutral 50 score
        is_noteworthy = (
            detected.deployer_token_count > 0 or  # We know this deployer
            detected.conviction_score >= 65 or     # Strong signal
            detected.status == "rejected" or        # Known bad actor
            len(detected.deployer_tags) > 0         # Has any deployer tags
        )

        if is_noteworthy:
            # Try to get token name (in background to not block)
            try:
                name, symbol = await asyncio.to_thread(self._fetch_token_name, token_address)
                if name:
                    detected.token_name = name
                if symbol:
                    detected.token_symbol = symbol
            except Exception:
                pass

            # Persist noteworthy detections
            self._persist_detection(detected)

            # Start 60-second watch window for crime coin detection
            # (only for non-rejected tokens — no point watching known ruggers)
            if detected.status != "rejected" and token_address not in self._watching:
                self._watching[token_address] = {
                    "detected": detected,
                    "buys": [],
                    "start_time": time.time(),
                    "creation_slot": creation_slot,
                }

            # Add to feed
            self._feed.insert(0, detected)
            if len(self._feed) > MAX_FEED_SIZE:
                self._feed = self._feed[:MAX_FEED_SIZE]

            log_info(
                f"[RealtimeListener] {'🟢' if detected.status == 'high_conviction' else '🔴' if detected.status == 'rejected' else '🟡'} "
                f"{detected.token_name or token_address[:12]}... score={detected.conviction_score} "
                f"deployer={'known' if detected.deployer_token_count > 0 else 'new'} "
                f"status={detected.status}"
            )

            # Fire callback if set
            if self._on_token_detected:
                try:
                    self._on_token_detected(detected)
                except Exception as e:
                    log_error(f"[RealtimeListener] Callback error: {e}")

            # Broadcast to frontend
            try:
                from meridinate.websocket import broadcast_message
                await broadcast_message({
                    "event": "realtime_token_detected",
                    "data": detected.to_dict(),
                })
            except Exception:
                pass

    def _extract_token_creation(self, tx: dict) -> Optional[Dict[str, Any]]:
        """
        Check if a transaction is a PumpFun token creation.
        Returns token info dict or None if not a creation event.
        """
        # Enhanced transaction format from Helius
        meta = tx.get("meta", {})
        transaction = tx.get("transaction", tx)
        signature = tx.get("signature") or transaction.get("signatures", [""])[0]

        # Look for new token mint in postTokenBalances that doesn't exist in preTokenBalances
        pre_mints = set()
        for bal in meta.get("preTokenBalances", []):
            pre_mints.add(bal.get("mint", ""))

        new_mints = []
        for bal in meta.get("postTokenBalances", []):
            mint = bal.get("mint", "")
            if mint and mint not in pre_mints:
                new_mints.append(mint)

        if not new_mints:
            return None

        # The fee payer is the deployer (first account in the transaction)
        accounts = transaction.get("message", {}).get("accountKeys", [])
        deployer = None
        if accounts:
            first = accounts[0]
            deployer = first.get("pubkey") if isinstance(first, dict) else first

        # Get initial SOL from fee payer's balance change
        initial_sol = 0
        pre_balances = meta.get("preBalances", [])
        post_balances = meta.get("postBalances", [])
        if pre_balances and post_balances:
            sol_spent = (pre_balances[0] - post_balances[0]) / 1e9
            initial_sol = max(0, sol_spent)

        # Get slot number from the transaction result
        slot = tx.get("slot", 0)

        return {
            "token_address": new_mints[0],
            "deployer_address": deployer,
            "initial_sol": initial_sol,
            "signature": signature,
            "slot": slot,
        }

    def _extract_buy_from_tx(self, tx: dict, token_address: str) -> Optional[Dict]:
        """Extract buy information from a transaction involving a watched token."""
        meta = tx.get("meta", {})
        transaction = tx.get("transaction", tx)
        slot = tx.get("slot", 0)

        # Check if this transaction involves the watched token
        post_balances = meta.get("postTokenBalances", [])
        involves_token = any(
            bal.get("mint") == token_address for bal in post_balances
        )
        if not involves_token:
            return None

        # Get the fee payer (buyer)
        accounts = transaction.get("message", {}).get("accountKeys", [])
        buyer = None
        if accounts:
            first = accounts[0]
            buyer = first.get("pubkey") if isinstance(first, dict) else first

        # Get SOL spent
        sol_spent = 0
        pre_bals = meta.get("preBalances", [])
        post_bals = meta.get("postBalances", [])
        if pre_bals and post_bals:
            sol_spent = max(0, (pre_bals[0] - post_bals[0]) / 1e9)

        if not buyer or sol_spent < 0.001:  # Ignore dust
            return None

        return {
            "buyer": buyer,
            "sol_spent": sol_spent,
            "slot": slot,
            "timestamp": time.time(),
        }

    async def _collect_watch_data(self, tx: dict):
        """Collect buy transactions for tokens in active watch windows."""
        if not self._watching:
            return

        meta = tx.get("meta", {})
        post_balances = meta.get("postTokenBalances", [])
        tx_mints = {bal.get("mint") for bal in post_balances if bal.get("mint")}

        for token_address in list(self._watching.keys()):
            if token_address in tx_mints:
                buy = self._extract_buy_from_tx(tx, token_address)
                if buy:
                    watch = self._watching[token_address]
                    # Don't add the deployer's own creation tx as a "buy"
                    if buy["buyer"] != watch["detected"].deployer_address:
                        watch["buys"].append(buy)

    async def _process_expired_watches(self):
        """Check for watch windows that have expired and run crime coin + market viability analysis."""
        from meridinate.settings import CURRENT_INGEST_SETTINGS
        watch_duration = CURRENT_INGEST_SETTINGS.get("realtime_watch_window_seconds", 300)

        now = time.time()
        expired = [addr for addr, w in self._watching.items() if now - w["start_time"] >= watch_duration]

        for token_address in expired:
            watch = self._watching.pop(token_address)
            detected = watch["detected"]
            buys = watch["buys"]
            creation_slot = watch["creation_slot"]

            # Run crime coin analysis
            crime_risk = self._analyze_crime_coin(detected, buys, creation_slot)

            # Update the detected token in the feed
            detected.crime_risk_score = crime_risk
            detected.watch_window_complete = True
            detected.total_buyers = len(set(b["buyer"] for b in buys))

            # Phase 1: Adjust conviction based on crime risk
            if crime_risk >= 70:
                detected.conviction_score = max(0, detected.conviction_score - 40)
                detected.status = "rejected"
                detected.rejection_reason = f"Crime coin pattern detected (risk={crime_risk})"
                self._stats["total_crime_coins"] = self._stats.get("total_crime_coins", 0) + 1
                self._stats["total_rejected"] += 1
                log_info(f"[RealtimeListener] 🚨 Crime coin detected: {detected.token_name or token_address[:12]}... risk={crime_risk}")
            else:
                # Phase 2: Market viability check (only for non-crime tokens)
                mc_min = CURRENT_INGEST_SETTINGS.get("realtime_mc_min_at_close", 5000)
                market_data = await asyncio.to_thread(self._check_market_viability, token_address)

                detected.mc_at_30s = market_data.get("mc", 0)

                if market_data.get("mc", 0) > 0:
                    current_mc = market_data["mc"]
                    volume = market_data.get("volume", 0)
                    liquidity = market_data.get("liquidity", 0)

                    if crime_risk < 30 and current_mc >= mc_min:
                        # Organic AND showing market traction
                        detected.conviction_score = min(100, detected.conviction_score + 15)
                        detected.social_proof_score = min(30, detected.social_proof_score + 15)
                        detected.status = "high_conviction"
                        self._stats["total_high_conviction"] += 1
                        log_info(
                            f"[RealtimeListener] 🟢 HIGH CONVICTION: {detected.token_name or token_address[:12]}... "
                            f"crime_risk={crime_risk}, MC=${current_mc:,.0f}, conviction={detected.conviction_score}"
                        )
                    elif crime_risk < 30 and current_mc < mc_min:
                        # Organic but weak market performance
                        detected.status = "weak"
                        log_info(
                            f"[RealtimeListener] ⚪ WEAK: {detected.token_name or token_address[:12]}... "
                            f"organic (risk={crime_risk}) but MC=${current_mc:,.0f} < ${mc_min:,.0f} threshold"
                        )
                    else:
                        # Mixed signals
                        detected.status = "watching"
                        log_info(
                            f"[RealtimeListener] 🟡 WATCHING: {detected.token_name or token_address[:12]}... "
                            f"crime_risk={crime_risk}, MC=${current_mc:,.0f}"
                        )
                else:
                    # Couldn't get market data — stay watching
                    if crime_risk < 30:
                        detected.conviction_score = min(100, detected.conviction_score + 5)
                    detected.status = "watching"

            # Update persisted detection
            self._persist_detection(detected)

            # Hand off to follow-up tracker for continued MC observation
            if detected.status != "rejected":
                try:
                    from meridinate.services.followup_tracker import get_followup_tracker
                    tracker = get_followup_tracker()
                    tracker.add_token(
                        token_address=token_address,
                        token_name=detected.token_name,
                        status=detected.status,
                        conviction_score=detected.conviction_score,
                        creation_time=detected.detected_at,
                    )
                except Exception as e:
                    log_error(f"[RealtimeListener] Follow-up handoff failed: {e}")

            # Broadcast update to frontend
            try:
                from meridinate.websocket import broadcast_message
                await broadcast_message({
                    "event": "realtime_token_updated",
                    "data": detected.to_dict(),
                })
            except Exception:
                pass

    def _analyze_crime_coin(self, detected: DetectedToken, buys: List[Dict], creation_slot: int) -> int:
        """
        Analyze collected buy data for crime coin patterns.
        Returns a risk score 0-100.

        Key principle: bundling and fresh wallets alone are NOT red flags.
        Many legitimate launches use coordinated initial buys for momentum.
        Risk comes from the COMBINATION of suspicious signals:
        - Bundled + fresh + shared funders + deployer linked = likely rug
        - Bundled + established wallets or deployer themselves = likely team launch
        """
        risk = 0
        red_flags = 0  # Count how many suspicious signals are present

        if not buys:
            return 0

        unique_buyers = set(b["buyer"] for b in buys)

        # 1. Bundle detection: record as data, not risk
        is_bundled = False
        if creation_slot > 0:
            early_buys = [b for b in buys if b["slot"] <= creation_slot + 3]
            detected.buys_in_first_3_blocks = len(early_buys)
            is_bundled = len(early_buys) >= 5

        # 2. Buy amount uniformity: record as data
        amounts = [b["sol_spent"] for b in buys if b["sol_spent"] > 0.01]
        is_uniform = False
        if len(amounts) >= 3:
            mean_amount = sum(amounts) / len(amounts)
            if mean_amount > 0:
                variance = sum((a - mean_amount) ** 2 for a in amounts) / len(amounts)
                std_dev = variance ** 0.5
                cv = std_dev / mean_amount
                detected.buy_amount_uniformity = round(cv, 3)
                is_uniform = cv < 0.15

        # 3. Check buyer characteristics (DB lookups — data collection, not direct risk)
        has_high_fresh_pct = False
        has_shared_funders = False
        has_deployer_link = False
        has_smart_buyers = False

        try:
            import sqlite3
            from meridinate.settings import DATABASE_FILE
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()

            buyer_list = list(unique_buyers)
            if buyer_list:
                placeholders = ",".join("?" for _ in buyer_list)

                # Fresh wallet check — record data
                cursor.execute(
                    f"SELECT COUNT(DISTINCT wallet_address) FROM wallet_tags "
                    f"WHERE wallet_address IN ({placeholders}) AND tag LIKE 'Fresh%'",
                    buyer_list
                )
                fresh_count = cursor.fetchone()[0]
                detected.fresh_buyer_count = fresh_count
                if len(unique_buyers) > 0:
                    detected.fresh_buyer_pct = round(fresh_count / len(unique_buyers) * 100, 1)
                    has_high_fresh_pct = detected.fresh_buyer_pct >= 60

                # Check if buyers share a funder (from wallet_enrichment_cache)
                cursor.execute(
                    f"SELECT funded_by_json FROM wallet_enrichment_cache "
                    f"WHERE wallet_address IN ({placeholders}) AND funded_by_json IS NOT NULL",
                    buyer_list
                )
                funders = {}
                for row in cursor.fetchall():
                    try:
                        fb = json.loads(row[0])
                        funder = fb.get("funder") if isinstance(fb, dict) else None
                        if funder:
                            funders.setdefault(funder, 0)
                            funders[funder] += 1
                    except Exception:
                        pass
                max_shared = max(funders.values()) if funders else 0
                detected.buyers_sharing_funder = max_shared
                has_shared_funders = max_shared >= 3

                # Check if deployer is linked to any buyer
                if detected.deployer_address:
                    cursor.execute(
                        f"SELECT funded_by_json FROM wallet_enrichment_cache WHERE wallet_address = ?",
                        (detected.deployer_address,)
                    )
                    deployer_funder_row = cursor.fetchone()
                    if deployer_funder_row and deployer_funder_row[0]:
                        try:
                            deployer_fb = json.loads(deployer_funder_row[0])
                            deployer_funder = deployer_fb.get("funder") if isinstance(deployer_fb, dict) else None
                            if deployer_funder and funders.get(deployer_funder, 0) > 0:
                                detected.deployer_linked_to_buyer = True
                                has_deployer_link = True
                        except Exception:
                            pass

                # Check if any buyers are known good wallets (excluding Sniper Bots)
                # First get sniper bot addresses to exclude
                cursor.execute(
                    f"SELECT DISTINCT wallet_address FROM wallet_tags "
                    f"WHERE wallet_address IN ({placeholders}) AND tag = 'Sniper Bot'",
                    buyer_list
                )
                sniper_bot_addrs = {row[0] for row in cursor.fetchall()}

                cursor.execute(
                    f"SELECT DISTINCT wallet_address, tag FROM wallet_tags "
                    f"WHERE wallet_address IN ({placeholders}) AND tag IN ('Consistent Winner', 'Sniper', 'High SOL Balance')",
                    buyer_list
                )
                smart_buyers = {}
                for row in cursor.fetchall():
                    if row[0] not in sniper_bot_addrs:  # Exclude sniper bots
                        smart_buyers[row[0]] = row[1]
                detected.smart_wallets_buying = len(smart_buyers)
                detected.smart_wallet_names = [f"{addr[:8]}...({tag})" for addr, tag in smart_buyers.items()]
                has_smart_buyers = len(smart_buyers) > 0

            conn.close()

        except Exception as e:
            log_error(f"[RealtimeListener] Crime coin DB analysis failed: {e}")

        # 4. Unique buyers in first 30 seconds
        buys_30s = [b for b in buys if b["timestamp"] - buys[0]["timestamp"] <= 30] if buys else []
        detected.unique_buyers_30s = len(set(b["buyer"] for b in buys_30s))

        # 5. Compute risk from COMBINATION of signals, not individual flags
        # Bundling alone = neutral (could be team launch)
        # Fresh wallets alone = neutral (could be new traders)
        # But bundled + fresh + shared funders = very suspicious

        # Count red flags
        if has_shared_funders:
            red_flags += 1
            risk += 15
        if has_deployer_link:
            red_flags += 1
            risk += 15
        if is_bundled and is_uniform:
            red_flags += 1  # Bundled with identical amounts = automated
            risk += 10
        if is_bundled and has_high_fresh_pct and has_shared_funders:
            # The classic crime coin combo: bundled + fresh + shared funder
            risk += 20

        # Smart wallets buying is a strong counter-signal
        if has_smart_buyers:
            risk -= 20  # Known good traders = legitimacy

        return max(0, min(100, risk))

    def _check_market_viability(self, token_address: str) -> Dict[str, Any]:
        """
        Check token's current market data from DexScreener.
        Free API call, runs in a thread to not block.
        """
        try:
            from meridinate.services.dexscreener_service import get_dexscreener_service
            dex = get_dexscreener_service()
            snapshot = dex.get_token_snapshot(token_address)
            if snapshot:
                return {
                    "mc": snapshot.get("market_cap_usd") or 0,
                    "volume": snapshot.get("volume_24h_usd") or 0,
                    "liquidity": snapshot.get("liquidity_usd") or 0,
                    "buys": snapshot.get("buys_24h") or 0,
                    "sells": snapshot.get("sells_24h") or 0,
                }
        except Exception as e:
            log_error(f"[RealtimeListener] Market viability check failed: {e}")
        return {"mc": 0, "volume": 0, "liquidity": 0}

    def _fetch_token_name(self, token_address: str) -> tuple:
        """Fetch token name from PumpFun API with DexScreener fallback. Runs in a thread."""
        import time as _time

        # Try PumpFun first (free, usually has new tokens fast)
        for attempt in range(3):
            try:
                from meridinate.services.pumpfun_service import get_pumpfun_token_data
                pf_data = get_pumpfun_token_data(token_address)
                if pf_data and pf_data.get("name"):
                    return pf_data.get("name"), pf_data.get("symbol")
            except Exception:
                pass
            if attempt < 2:
                _time.sleep(2)  # Wait 2 seconds before retry

        # Fallback to DexScreener
        try:
            from meridinate.services.dexscreener_service import get_dexscreener_service
            dex = get_dexscreener_service()
            snapshot = dex.get_token_snapshot(token_address)
            if snapshot:
                return snapshot.get("token_name"), snapshot.get("token_symbol")
        except Exception:
            pass
        return None, None

    def _persist_detection(self, token: DetectedToken):
        """Save detection to webhook_detections table."""
        try:
            import sqlite3
            from meridinate.settings import DATABASE_FILE

            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO webhook_detections (
                    token_address, deployer_address, detected_at, signature,
                    initial_sol, conviction_score, deployer_score, safety_score,
                    social_proof_score, deployer_token_count, deployer_win_rate,
                    deployer_tags_json, status, rejection_reason,
                    token_name, token_symbol
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(token_address) DO UPDATE SET
                    conviction_score = excluded.conviction_score,
                    deployer_score = excluded.deployer_score,
                    safety_score = excluded.safety_score,
                    social_proof_score = excluded.social_proof_score,
                    status = excluded.status,
                    rejection_reason = excluded.rejection_reason,
                    token_name = COALESCE(excluded.token_name, webhook_detections.token_name),
                    token_symbol = COALESCE(excluded.token_symbol, webhook_detections.token_symbol)
            """, (
                token.token_address, token.deployer_address, token.detected_at,
                token.signature, token.initial_sol, token.conviction_score,
                token.deployer_score, token.safety_score, token.social_proof_score,
                token.deployer_token_count, token.deployer_win_rate,
                json.dumps(token.deployer_tags), token.status, token.rejection_reason,
                token.token_name, token.token_symbol,
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            log_error(f"[RealtimeListener] Failed to persist detection: {e}")

    async def _compute_conviction(self, token: DetectedToken):
        """
        Compute conviction score for a detected token.
        Uses database lookups — no external API calls for speed.
        """
        import sqlite3
        from meridinate.settings import DATABASE_FILE

        deployer_score = 0
        safety_score = 0
        social_proof_score = 0

        try:
            conn = sqlite3.connect(DATABASE_FILE)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if token.deployer_address:
                # Check deployer history
                cursor.execute("""
                    SELECT COUNT(*) as cnt,
                           deployer_address
                    FROM analyzed_tokens
                    WHERE deployer_address = ? AND (deleted_at IS NULL OR deleted_at = '')
                """, (token.deployer_address,))
                dep_row = cursor.fetchone()
                token.deployer_token_count = dep_row["cnt"] if dep_row else 0

                if token.deployer_token_count > 0:
                    # Get deployer's win/loss record
                    cursor.execute("""
                        SELECT
                            SUM(CASE WHEN (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = t.id AND tt.tag = 'verified-win' LIMIT 1) IS NOT NULL THEN 1 ELSE 0 END) as wins,
                            SUM(CASE WHEN (SELECT tt.tag FROM token_tags tt WHERE tt.token_id = t.id AND tt.tag = 'verified-loss' LIMIT 1) IS NOT NULL THEN 1 ELSE 0 END) as losses
                        FROM analyzed_tokens t
                        WHERE t.deployer_address = ? AND (t.deleted_at IS NULL OR t.deleted_at = '')
                    """, (token.deployer_address,))
                    verdict_row = cursor.fetchone()
                    wins = verdict_row["wins"] or 0
                    losses = verdict_row["losses"] or 0
                    total_verdicts = wins + losses

                    if total_verdicts > 0:
                        token.deployer_win_rate = wins / total_verdicts

                    # Score based on deployer track record
                    if total_verdicts >= 2 and token.deployer_win_rate and token.deployer_win_rate >= 0.5:
                        deployer_score += 30  # Known winning deployer
                    elif total_verdicts >= 2 and token.deployer_win_rate is not None and token.deployer_win_rate < 0.3:
                        deployer_score -= 40  # Known rug deployer — instant reject
                        token.status = "rejected"
                        token.rejection_reason = f"Known rug deployer ({wins}/{total_verdicts} wins)"
                    elif token.deployer_token_count >= 3 and wins == 0:
                        deployer_score -= 20  # Serial deployer, no wins
                    else:
                        deployer_score += 5  # Some history, neutral
                else:
                    deployer_score += 5  # Unknown deployer — neutral

                # Check deployer wallet tags
                cursor.execute(
                    "SELECT tag FROM wallet_tags WHERE wallet_address = ?",
                    (token.deployer_address,)
                )
                token.deployer_tags = [row["tag"] for row in cursor.fetchall()]

                if "Winning Deployer" in token.deployer_tags:
                    deployer_score += 10
                if "Rug Deployer" in token.deployer_tags:
                    deployer_score -= 30
                    if token.status != "rejected":
                        token.status = "rejected"
                        token.rejection_reason = "Tagged as Rug Deployer"
                if "Deployer Network" in token.deployer_tags:
                    deployer_score -= 10
                if "Serial Deployer" in token.deployer_tags and token.deployer_win_rate is not None and token.deployer_win_rate < 0.3:
                    deployer_score -= 10

            # Safety score from initial SOL
            if token.initial_sol > 1.0:
                safety_score += 5  # Deployer put real SOL in
            elif token.initial_sol > 5.0:
                safety_score += 10

            conn.close()

        except Exception as e:
            log_error(f"[RealtimeListener] Conviction scoring error: {e}")

        # Compute final score
        token.deployer_score = max(-40, min(40, deployer_score))
        token.safety_score = max(0, min(30, safety_score))
        token.social_proof_score = max(0, min(30, social_proof_score))  # Fills in later
        token.conviction_score = max(0, min(100, 50 + token.deployer_score + token.safety_score + token.social_proof_score))

        # Set status based on score
        if token.status != "rejected":
            if token.conviction_score >= 70:
                token.status = "high_conviction"
            elif token.conviction_score < 30:
                token.status = "rejected"
                if not token.rejection_reason:
                    token.rejection_reason = "Low conviction score"
            else:
                token.status = "watching"

        # Token name fetched later for noteworthy tokens only (saves API calls)


# Singleton
_listener: Optional[RealtimeListener] = None


def get_realtime_listener() -> RealtimeListener:
    global _listener
    if _listener is None:
        _listener = RealtimeListener(HELIUS_API_KEY)
    return _listener
