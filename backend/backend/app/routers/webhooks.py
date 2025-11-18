"""
Webhooks router - webhook management endpoints

Provides REST endpoints for creating and managing Helius webhooks
"""

import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

import analyzed_tokens_db as db
from app.settings import HELIUS_API_KEY
from app.state import WEBHOOK_EXECUTOR
from app.utils.models import CreateWebhookRequest
from helius_api import WebhookManager

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


@router.post("/webhooks/callback")
async def webhook_callback(request: Request):
    """Receive webhook notifications from Helius"""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    transactions = payload if isinstance(payload, list) else [payload]

    for tx in transactions:
        signature = tx.get("signature")
        timestamp = tx.get("timestamp")
        tx_type = tx.get("type")
        description = tx.get("description", "")
        native_transfers = tx.get("nativeTransfers", [])
        token_transfers = tx.get("tokenTransfers", [])

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
                print(f"[Webhook] Saved activity for wallet {wallet_address[:8]}...")
            except Exception as exc:
                print(f"[Webhook] Failed to save activity: {exc}")

    return {"status": "success", "processed": len(transactions)}
