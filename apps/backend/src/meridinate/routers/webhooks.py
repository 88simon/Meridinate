"""
Webhooks router - webhook management endpoints

Provides REST endpoints for creating and managing Helius webhooks.

SWAB Integration:
When a token transfer is received where a tracked MTEW wallet is the sender
(fromUserAccount), this indicates a potential sell. The callback will:
1. Look up if the wallet has an active MTEW position for that token
2. Get current token price from DexScreener
3. Calculate USD value of the sell
4. Record the position sell with accurate price data

This webhook-first approach captures sells before transactions scroll out
of the recent signature window, ensuring accurate PnL calculations.
"""

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from meridinate import analyzed_tokens_db as db
from meridinate.settings import HELIUS_API_KEY
from meridinate.state import WEBHOOK_EXECUTOR
from meridinate.utils.models import CreateWebhookRequest
from meridinate.helius_api import WebhookManager, HeliusAPI

router = APIRouter()


def _require_helius():
    if not HELIUS_API_KEY:
        raise HTTPException(status_code=503, detail="Helius API not available")


async def _run_webhook_task(func):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(WEBHOOK_EXECUTOR, func)


@router.post("/webhooks/create", status_code=202)
async def create_webhook(payload: CreateWebhookRequest):
    """Create a Helius webhook for monitoring token wallets"""
    _require_helius()
    token_details = db.get_token_details(payload.token_id)
    if not token_details:
        raise HTTPException(status_code=404, detail="Token not found")

    wallets = token_details.get("wallets", [])
    if not wallets:
        raise HTTPException(status_code=400, detail="No wallets found for this token")

    wallet_addresses = [w["wallet_address"] for w in wallets]
    callback_url = payload.webhook_url or "http://localhost:5003/webhooks/callback"

    def worker():
        try:
            manager = WebhookManager(HELIUS_API_KEY)
            result = manager.create_webhook(
                webhook_url=callback_url, wallet_addresses=wallet_addresses, transaction_types=["TRANSFER", "SWAP"]
            )
            webhook_id = result.get("webhookID")
            print(f"[Webhook] Created webhook {webhook_id} for token {payload.token_id}")
            return result
        except Exception as exc:
            print(f"[Webhook] Error creating webhook: {exc}")
            return None

    WEBHOOK_EXECUTOR.submit(worker)

    return {
        "status": "queued",
        "message": "Webhook creation queued",
        "token_id": payload.token_id,
        "wallets_monitored": len(wallet_addresses),
    }


@router.get("/webhooks/list")
async def list_webhooks():
    """List all webhooks for this API key"""
    _require_helius()

    def worker():
        manager = WebhookManager(HELIUS_API_KEY)
        return manager.list_webhooks()

    try:
        webhooks = await _run_webhook_task(worker)
        return {"total": len(webhooks), "webhooks": webhooks}
    except Exception as exc:
        print(f"[Webhook] Error listing webhooks: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/webhooks/{webhook_id}")
async def get_webhook_details(webhook_id: str):
    """Get details of a specific webhook"""
    _require_helius()

    def worker():
        manager = WebhookManager(HELIUS_API_KEY)
        return manager.get_webhook(webhook_id)

    webhook = await _run_webhook_task(worker)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook


@router.delete("/webhooks/{webhook_id}", status_code=202)
async def delete_webhook(webhook_id: str):
    """Delete a webhook"""
    _require_helius()

    def worker():
        manager = WebhookManager(HELIUS_API_KEY)
        manager.delete_webhook(webhook_id)
        print(f"[Webhook] Deleted webhook {webhook_id}")

    WEBHOOK_EXECUTOR.submit(worker)
    return {"status": "queued", "message": f"Webhook {webhook_id} deletion queued"}


@router.post("/webhooks/create-swab", status_code=202)
async def create_swab_webhook(request: Request):
    """
    Create a Helius webhook for all active SWAB positions.

    This creates a single webhook monitoring all MTEW wallets that have
    active (still holding) positions. When any of these wallets sends
    tokens, the webhook callback will detect potential sells and update
    positions in real-time.

    Request body (optional):
    - webhook_url: Custom callback URL (default: http://localhost:5003/webhooks/callback)

    Returns:
    - status: "queued" or "error"
    - wallets_count: Number of wallets being monitored
    - webhook_url: The callback URL configured
    """
    _require_helius()

    # Get all active SWAB wallets
    wallet_addresses = db.get_active_swab_wallets()

    if not wallet_addresses:
        raise HTTPException(
            status_code=400,
            detail="No active SWAB positions found. Analyze tokens and enable position tracking first."
        )

    # Parse optional callback URL from request body
    try:
        body = await request.json()
        callback_url = body.get("webhook_url", "http://localhost:5003/webhooks/callback")
    except Exception:
        callback_url = "http://localhost:5003/webhooks/callback"

    def worker():
        try:
            manager = WebhookManager(HELIUS_API_KEY)
            result = manager.create_webhook(
                webhook_url=callback_url,
                wallet_addresses=wallet_addresses,
                transaction_types=["TRANSFER", "SWAP"]
            )
            webhook_id = result.get("webhookID")
            print(
                f"[Webhook/SWAB] Created webhook {webhook_id} "
                f"monitoring {len(wallet_addresses)} MTEW wallets"
            )
            return result
        except Exception as exc:
            print(f"[Webhook/SWAB] Error creating webhook: {exc}")
            return None

    WEBHOOK_EXECUTOR.submit(worker)

    return {
        "status": "queued",
        "message": "SWAB webhook creation queued",
        "wallets_count": len(wallet_addresses),
        "webhook_url": callback_url,
        "wallets_preview": wallet_addresses[:5] if len(wallet_addresses) > 5 else wallet_addresses,
    }


def _process_swab_buy(
    wallet_address: str,
    token_mint: str,
    tokens_bought: float,
    signature: str,
) -> Optional[str]:
    """
    Process a potential SWAB position buy (DCA or re-entry) detected via webhook.

    When a tracked wallet receives tokens, we update their cost basis with
    accurate real-time price data.

    Args:
        wallet_address: The wallet that received tokens (buyer)
        token_mint: Token mint address
        tokens_bought: Number of tokens received
        signature: Transaction signature for logging

    Returns:
        Result message or None if not a tracked position
    """
    # Look up if this wallet has ANY position for this token (including sold)
    position = db.get_position_by_token_address(wallet_address, token_mint)
    if not position:
        return None  # Not a tracked MTEW position

    token_id = position["token_id"]
    token_symbol = position.get("token_symbol", "???")
    current_balance = position.get("current_balance", 0) or 0
    was_holding = position.get("still_holding", False)

    # Get current token price from DexScreener
    try:
        helius = HeliusAPI(HELIUS_API_KEY)
        token_price = helius.get_token_price_from_dexscreener(token_mint)
    except Exception as e:
        print(f"[Webhook/SWAB] Failed to get price for {token_symbol}: {e}")
        token_price = None

    if not token_price:
        print(f"[Webhook/SWAB] No price available for {token_symbol}, skipping buy update")
        return None

    # Calculate USD value of the buy
    usd_amount = tokens_bought * token_price

    # Calculate new balance after buy
    new_balance = current_balance + tokens_bought
    new_balance_usd = new_balance * token_price

    # Record the buy with accurate real-time price data
    try:
        success = db.record_position_buy(
            wallet_address=wallet_address,
            token_id=token_id,
            tokens_bought=tokens_bought,
            usd_amount=usd_amount,
            current_balance=new_balance,
            current_balance_usd=new_balance_usd,
        )

        if success:
            buy_type = "RE-ENTRY" if not was_holding else "DCA"
            print(
                f"[Webhook/SWAB] {buy_type} {wallet_address[:8]}... "
                f"bought {tokens_bought:.2f} {token_symbol} for ${usd_amount:.2f} "
                f"(tx: {signature[:12]}...)"
            )
            return f"{buy_type}: {tokens_bought:.2f} {token_symbol} for ${usd_amount:.2f}"
        else:
            print(f"[Webhook/SWAB] Failed to record buy for {wallet_address[:8]}...")
            return None

    except Exception as e:
        print(f"[Webhook/SWAB] Error recording buy: {e}")
        return None


def _process_swab_sell(
    wallet_address: str,
    token_mint: str,
    tokens_sold: float,
    signature: str,
) -> Optional[str]:
    """
    Process a potential SWAB position sell detected via webhook.

    This is the webhook-first approach: we capture the sell in real-time
    with accurate price data before the transaction scrolls out of history.

    Args:
        wallet_address: The wallet that sent tokens (seller)
        token_mint: Token mint address
        tokens_sold: Number of tokens transferred out
        signature: Transaction signature for logging

    Returns:
        Result message or None if not a tracked position
    """
    # Look up if this wallet has an active position for this token
    position = db.get_active_position_by_token_address(wallet_address, token_mint)
    if not position:
        return None  # Not a tracked MTEW position

    token_id = position["token_id"]
    token_symbol = position.get("token_symbol", "???")
    current_balance = position.get("current_balance", 0) or 0
    entry_balance = position.get("entry_balance") or position.get("total_bought_tokens") or current_balance
    avg_entry_price = position.get("avg_entry_price")
    total_bought_usd = position.get("total_bought_usd")
    entry_mc = position.get("entry_market_cap")

    # Get current token price from DexScreener (real-time, this is the exit price!)
    try:
        helius = HeliusAPI(HELIUS_API_KEY)
        token_price = helius.get_token_price_from_dexscreener(token_mint)
        current_mc = helius.get_market_cap_from_dexscreener(token_mint)
    except Exception as e:
        print(f"[Webhook/SWAB] Failed to get price for {token_symbol}: {e}")
        token_price = None
        current_mc = None

    if not token_price:
        print(f"[Webhook/SWAB] No price available for {token_symbol}, skipping position update")
        return None

    # Calculate USD value received from the sell (tokens_sold * current_price)
    usd_received = tokens_sold * token_price

    # Calculate new balance after sell
    new_balance = max(0, current_balance - tokens_sold)

    # Determine if this is a full exit (balance goes to 0 or very close)
    is_full_exit = new_balance < 0.001 or tokens_sold >= (current_balance * 0.99)

    # Calculate new balance USD
    new_balance_usd = new_balance * token_price if new_balance > 0 else 0

    # Record the sell with accurate real-time price data
    try:
        success = db.record_position_sell(
            wallet_address=wallet_address,
            token_id=token_id,
            tokens_sold=tokens_sold,
            usd_received=usd_received,
            current_balance=new_balance,
            current_balance_usd=new_balance_usd,
            is_full_exit=is_full_exit,
            exit_market_cap=current_mc if is_full_exit else None,
            entry_market_cap=entry_mc,
            current_market_cap=current_mc,
        )

        if success:
            exit_type = "FULL EXIT" if is_full_exit else "PARTIAL SELL"
            # Calculate PnL for logging
            pnl_str = ""
            if avg_entry_price and avg_entry_price > 0:
                exit_price = usd_received / tokens_sold if tokens_sold > 0 else 0
                pnl_ratio = exit_price / avg_entry_price
                pnl_str = f" PnL: {pnl_ratio:.2f}x"

            print(
                f"[Webhook/SWAB] {exit_type} {wallet_address[:8]}... "
                f"sold {tokens_sold:.2f} {token_symbol} for ${usd_received:.2f}{pnl_str} "
                f"(tx: {signature[:12]}...)"
            )
            return f"{exit_type}: {tokens_sold:.2f} {token_symbol} for ${usd_received:.2f}"
        else:
            print(f"[Webhook/SWAB] Failed to record sell for {wallet_address[:8]}...")
            return None

    except Exception as e:
        print(f"[Webhook/SWAB] Error recording sell: {e}")
        return None


@router.post("/webhooks/callback")
async def webhook_callback(request: Request):
    """
    Receive webhook notifications from Helius.

    Processes token transfers to detect SWAB position updates in real-time:
    - SELL: When tracked wallet sends tokens (fromUserAccount), capture exit price
    - BUY/DCA: When tracked wallet receives tokens (toUserAccount), update cost basis
    - RE-ENTRY: When a sold position buys again, reactivate and record buy

    This webhook-first approach captures accurate prices before transactions
    scroll out of the recent signature window.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    transactions = payload if isinstance(payload, list) else [payload]
    swab_updates = 0

    for tx in transactions:
        signature = tx.get("signature", "")
        timestamp = tx.get("timestamp")
        tx_type = tx.get("type")
        description = tx.get("description", "")
        native_transfers = tx.get("nativeTransfers", [])
        token_transfers = tx.get("tokenTransfers", [])

        # Process token transfers for SWAB position updates
        for transfer in token_transfers:
            from_wallet = transfer.get("fromUserAccount")
            to_wallet = transfer.get("toUserAccount")
            token_mint = transfer.get("mint")
            token_amount = float(transfer.get("tokenAmount", 0))

            if not token_mint or token_amount <= 0:
                continue

            # If wallet is sending tokens (potential sell), check SWAB
            if from_wallet:
                result = _process_swab_sell(
                    wallet_address=from_wallet,
                    token_mint=token_mint,
                    tokens_sold=token_amount,
                    signature=signature,
                )
                if result:
                    swab_updates += 1

            # If wallet is receiving tokens (potential buy/DCA), check SWAB
            if to_wallet:
                result = _process_swab_buy(
                    wallet_address=to_wallet,
                    token_mint=token_mint,
                    tokens_bought=token_amount,
                    signature=signature,
                )
                if result:
                    swab_updates += 1

        # Save all transfers to wallet_activity (existing behavior)
        for transfer in native_transfers + token_transfers:
            wallet_address = transfer.get("fromUserAccount") or transfer.get("toUserAccount")
            if not wallet_address:
                continue

            if transfer in native_transfers:
                sol_amount = transfer.get("amount", 0) / 1e9
                token_amount = 0.0
                recipient = transfer.get("toUserAccount")
            else:
                sol_amount = 0.0
                token_amount = float(transfer.get("tokenAmount", 0))
                recipient = transfer.get("toUserAccount")

            try:
                db.save_wallet_activity(
                    wallet_address=wallet_address,
                    transaction_signature=signature,
                    timestamp=datetime.utcfromtimestamp(timestamp).isoformat() if timestamp else None,
                    activity_type=tx_type,
                    description=description,
                    sol_amount=sol_amount,
                    token_amount=token_amount,
                    recipient_address=recipient,
                )
            except Exception as exc:
                print(f"[Webhook] Failed to save activity: {exc}")

    return {
        "status": "success",
        "processed": len(transactions),
        "swab_updates": swab_updates,
    }
