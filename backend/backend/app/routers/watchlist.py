"""
Watchlist router - address monitoring endpoints

Provides REST endpoints for managing monitored wallet addresses
"""

from fastapi import APIRouter, HTTPException

from app.services.watchlist_service import get_watchlist_service
from app.utils.models import AddressNoteRequest, ImportAddressesRequest, RegisterAddressRequest
from app.utils.validators import is_valid_solana_address
from secure_logging import log_address_registered, log_address_removed, log_success, log_warning, sanitize_address

router = APIRouter()


@router.post("/register")
async def register_address(payload: RegisterAddressRequest):
    """
    Register a wallet address for monitoring

    Args:
        payload: Address and optional note

    Returns:
        Registration status and details
    """
    address = payload.address.strip()
    if not is_valid_solana_address(address):
        raise HTTPException(status_code=400, detail="Invalid Solana address format")

    service = get_watchlist_service()
    try:
        result = service.register_address(address, payload.note.strip() if payload.note else None)

        if result["status"] == "success":
            log_address_registered(sanitize_address(address))

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/addresses")
async def list_addresses():
    """
    Get list of all monitored addresses

    Returns:
        Total count and list of addresses
    """
    service = get_watchlist_service()
    return service.list_addresses()


@router.get("/address/{address}")
async def get_address(address: str):
    """
    Get details of a specific monitored address

    Args:
        address: Solana wallet address

    Returns:
        Address details
    """
    service = get_watchlist_service()
    address_data = service.get_address(address)
    if not address_data:
        raise HTTPException(status_code=404, detail="Address not found")
    return address_data


@router.delete("/address/{address}")
async def delete_address(address: str):
    """
    Remove an address from monitoring

    Args:
        address: Solana wallet address

    Returns:
        Deletion status
    """
    service = get_watchlist_service()
    try:
        result = service.unregister_address(address)
        log_address_removed(sanitize_address(address))
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/address/{address}/note")
async def update_address_note(address: str, payload: AddressNoteRequest):
    """
    Update the note for a monitored address

    Args:
        address: Solana wallet address
        payload: New note text

    Returns:
        Update status
    """
    service = get_watchlist_service()
    try:
        result = service.update_note(address, payload.note.strip() if payload.note else None)
        log_success(f"Updated note for address {sanitize_address(address)}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/import")
async def import_addresses(payload: ImportAddressesRequest):
    """
    Import multiple addresses at once

    Args:
        payload: List of address entries

    Returns:
        Import summary
    """
    service = get_watchlist_service()

    # Validate addresses
    valid_entries = []
    for entry in payload.addresses:
        if is_valid_solana_address(entry.address.strip()):
            valid_entries.append(
                {
                    "address": entry.address.strip(),
                    "registered_at": entry.registered_at,
                    "threshold": entry.threshold,
                    "total_notifications": entry.total_notifications,
                    "last_notification": entry.last_notification,
                    "note": entry.note,
                }
            )

    return service.import_addresses(valid_entries)


@router.post("/clear")
async def clear_addresses():
    """
    Clear all monitored addresses

    Returns:
        Clearing status
    """
    service = get_watchlist_service()
    result = service.clear_all()
    log_warning(f"Cleared all monitored addresses")
    return result
