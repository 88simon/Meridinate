"""
Application state management

Centralizes in-memory state stores:
- Analysis job tracking
- Monitored addresses (watchlist)
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

# ============================================================================
# Analysis Job Tracking
# ============================================================================

# In-memory job tracking (will be replaced with database or Redis in future)
analysis_jobs: Dict[str, Dict[str, Any]] = {}

# Thread pool for background analysis jobs
ANALYSIS_EXECUTOR = ThreadPoolExecutor(max_workers=10, thread_name_prefix="analysis")
WEBHOOK_EXECUTOR = ThreadPoolExecutor(max_workers=5, thread_name_prefix="webhook")


def get_analysis_job(job_id: str) -> Dict[str, Any]:
    """
    Get analysis job by ID

    Args:
        job_id: Job ID to look up

    Returns:
        Job dictionary or None if not found
    """
    return analysis_jobs.get(job_id)


def set_analysis_job(job_id: str, job_data: Dict[str, Any]):
    """
    Store or update analysis job data

    Args:
        job_id: Job ID
        job_data: Job data dictionary
    """
    analysis_jobs[job_id] = job_data


def update_analysis_job(job_id: str, updates: Dict[str, Any]):
    """
    Update specific fields of an analysis job

    Args:
        job_id: Job ID
        updates: Dictionary of fields to update
    """
    if job_id in analysis_jobs:
        analysis_jobs[job_id].update(updates)


def get_all_analysis_jobs() -> Dict[str, Dict[str, Any]]:
    """
    Get all analysis jobs

    Returns:
        Dictionary of all jobs
    """
    return analysis_jobs


# ============================================================================
# Monitored Addresses (Watchlist)
# ============================================================================

# In-memory monitored addresses store (loaded from/saved to JSON)
# Format: {address: {address, registered_at, threshold, total_notifications, last_notification, note}}
monitored_addresses: Dict[str, Dict[str, Any]] = {}


def get_monitored_address(address: str) -> Dict[str, Any]:
    """
    Get monitored address by address

    Args:
        address: Solana address

    Returns:
        Address data dictionary or None if not found
    """
    return monitored_addresses.get(address)


def set_monitored_address(address: str, data: Dict[str, Any]):
    """
    Store or update monitored address data

    Args:
        address: Solana address
        data: Address data dictionary
    """
    monitored_addresses[address] = data


def remove_monitored_address(address: str) -> bool:
    """
    Remove monitored address

    Args:
        address: Solana address

    Returns:
        True if removed, False if not found
    """
    if address in monitored_addresses:
        del monitored_addresses[address]
        return True
    return False


def get_all_monitored_addresses() -> Dict[str, Dict[str, Any]]:
    """
    Get all monitored addresses

    Returns:
        Dictionary of all monitored addresses
    """
    return monitored_addresses


def clear_monitored_addresses():
    """Clear all monitored addresses"""
    monitored_addresses.clear()


def get_monitored_address_count() -> int:
    """
    Get count of monitored addresses

    Returns:
        Number of monitored addresses
    """
    return len(monitored_addresses)
