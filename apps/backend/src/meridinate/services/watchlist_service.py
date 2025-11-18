"""
Watchlist service - manages monitored addresses

Handles loading, saving, and manipulating the watchlist (monitored addresses)
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from meridinate import settings
from meridinate.state import (
    clear_monitored_addresses,
    get_all_monitored_addresses,
    get_monitored_address,
    get_monitored_address_count,
    monitored_addresses,
    remove_monitored_address,
    set_monitored_address,
)


class WatchlistService:
    """Service for managing monitored wallet addresses"""

    def __init__(self):
        """Initialize watchlist service and load addresses from disk"""
        self.load_addresses()

    def load_addresses(self):
        """Load monitored addresses from JSON file"""
        if os.path.exists(settings.DATA_FILE):
            try:
                with open(settings.DATA_FILE, "r") as f:
                    data = json.load(f)
                    # Update the state
                    monitored_addresses.clear()
                    monitored_addresses.update(data)
                print(f"[Watchlist] Loaded {len(monitored_addresses)} monitored addresses from disk")
            except Exception as exc:
                print(f"[Watchlist] Failed to load monitored addresses: {exc}")
                monitored_addresses.clear()
        else:
            monitored_addresses.clear()

    def save_addresses(self) -> bool:
        """Persist monitored addresses to JSON"""
        try:
            with open(settings.DATA_FILE, "w") as f:
                json.dump(get_all_monitored_addresses(), f, indent=2)
            return True
        except Exception as exc:
            print(f"[Watchlist] Failed to save addresses: {exc}")
            return False

    def register_address(self, address: str, note: Optional[str] = None) -> Dict[str, Any]:
        """
        Register a new address for monitoring

        Args:
            address: Solana address to monitor
            note: Optional note about this address

        Returns:
            Dictionary with status and address data
        """
        existing = get_monitored_address(address)
        if existing:
            return {
                "status": "already_registered",
                "message": "Address already being monitored",
                "address": address,
                "registered_at": existing.get("registered_at"),
            }

        address_data = {
            "address": address,
            "registered_at": datetime.now().isoformat(),
            "threshold": settings.DEFAULT_THRESHOLD,
            "total_notifications": 0,
            "last_notification": None,
            "note": note,
        }

        set_monitored_address(address, address_data)

        if not self.save_addresses():
            remove_monitored_address(address)
            raise Exception("Failed to save address")

        return {
            "status": "success",
            "message": "Address registered for monitoring",
            "address": address,
            "threshold": settings.DEFAULT_THRESHOLD,
            "total_monitored": get_monitored_address_count(),
        }

    def get_address(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Get details of a monitored address

        Args:
            address: Solana address

        Returns:
            Address data dictionary or None
        """
        return get_monitored_address(address)

    def list_addresses(self) -> Dict[str, Any]:
        """
        Get list of all monitored addresses

        Returns:
            Dictionary with total and addresses list
        """
        addresses = get_all_monitored_addresses()
        return {"total": len(addresses), "addresses": list(addresses.values())}

    def unregister_address(self, address: str) -> Dict[str, Any]:
        """
        Remove address from monitoring

        Args:
            address: Solana address to remove

        Returns:
            Status dictionary
        """
        if not get_monitored_address(address):
            raise ValueError("Address not found")

        remove_monitored_address(address)
        self.save_addresses()

        return {"status": "success", "message": "Address removed from monitoring", "address": address}

    def update_note(self, address: str, note: Optional[str]) -> Dict[str, Any]:
        """
        Update the note for a monitored address

        Args:
            address: Solana address
            note: New note text or None to clear

        Returns:
            Status dictionary
        """
        address_data = get_monitored_address(address)
        if not address_data:
            raise ValueError("Address not found")

        address_data["note"] = note
        set_monitored_address(address, address_data)
        self.save_addresses()

        return {"status": "success", "message": "Note updated successfully", "address": address, "note": note}

    def import_addresses(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Import multiple addresses at once

        Args:
            entries: List of address entry dictionaries

        Returns:
            Import result summary
        """
        added = 0
        skipped = 0

        for entry in entries:
            address = entry.get("address", "").strip()
            if not address:
                skipped += 1
                continue

            if get_monitored_address(address):
                skipped += 1
                continue

            address_data = {
                "address": address,
                "registered_at": entry.get("registered_at") or datetime.now().isoformat(),
                "threshold": entry.get("threshold") or settings.DEFAULT_THRESHOLD,
                "total_notifications": entry.get("total_notifications") or 0,
                "last_notification": entry.get("last_notification"),
                "note": entry.get("note"),
            }

            set_monitored_address(address, address_data)
            added += 1

        self.save_addresses()

        return {
            "status": "success",
            "message": f"Imported {added} addresses ({skipped} duplicates skipped)",
            "added": added,
            "skipped": skipped,
            "total": get_monitored_address_count(),
        }

    def clear_all(self) -> Dict[str, Any]:
        """
        Clear all monitored addresses

        Returns:
            Status dictionary
        """
        count = get_monitored_address_count()
        clear_monitored_addresses()
        self.save_addresses()

        return {"status": "success", "message": f"Cleared {count} addresses", "total_monitored": 0}


# Singleton instance
_watchlist_service: Optional[WatchlistService] = None


def get_watchlist_service() -> WatchlistService:
    """
    Get the global WatchlistService instance

    Returns:
        WatchlistService singleton
    """
    global _watchlist_service
    if _watchlist_service is None:
        _watchlist_service = WatchlistService()
    return _watchlist_service
