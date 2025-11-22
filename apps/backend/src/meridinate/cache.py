"""
Response caching with ETags and request deduplication

Provides fast response caching to reduce database load and improve performance
"""

import asyncio
import hashlib
import time
from typing import Any, Dict, Optional, Tuple


# Import metrics_collector for tracking cache hits/misses
# This is optional - if not available, metrics won't be recorded
try:
    from meridinate.observability import metrics_collector

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    metrics_collector = None


class ResponseCache:
    """
    Cache for API responses with ETag support and request deduplication

    Features:
    - TTL-based expiration (default: 30 seconds)
    - ETag generation for conditional requests (304 Not Modified)
    - Request deduplication to prevent duplicate concurrent queries
    """

    def __init__(self, ttl: int = 30, name: str = "unknown"):
        """
        Initialize response cache

        Args:
            ttl: Time-to-live in seconds (default: 30)
            name: Cache name for metrics tracking (default: "unknown")
        """
        self.cache: Dict[str, Tuple[Any, float, str]] = {}  # (data, timestamp, etag)
        self.pending_requests: Dict[str, asyncio.Future] = {}  # Request deduplication
        self.ttl = ttl
        self.name = name

    def get(self, key: str) -> Tuple[Optional[Any], Optional[str]]:
        """
        Get cached value with ETag if still valid

        Args:
            key: Cache key

        Returns:
            Tuple of (data, etag) or (None, None) if not found/expired
        """
        if key in self.cache:
            data, timestamp, etag = self.cache[key]
            if time.time() - timestamp < self.ttl:
                # Record cache hit
                if METRICS_AVAILABLE and metrics_collector:
                    metrics_collector.record_cache_hit(self.name)
                return (data, etag)
            # Expired, delete and record as miss
            del self.cache[key]

        # Record cache miss
        if METRICS_AVAILABLE and metrics_collector:
            metrics_collector.record_cache_miss(self.name)

        return (None, None)

    def set(self, key: str, data: Any) -> str:
        """
        Store value with timestamp and generate ETag

        Args:
            key: Cache key
            data: Data to cache

        Returns:
            Generated ETag string
        """
        etag = self._generate_etag(data)
        self.cache[key] = (data, time.time(), etag)
        return etag

    def _generate_etag(self, data: Any) -> str:
        """
        Generate ETag from response data

        Args:
            data: Data to generate ETag for

        Returns:
            MD5 hash as ETag
        """
        import json

        content = json.dumps(data, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()

    def invalidate(self, pattern: str):
        """
        Invalidate cache entries matching pattern

        Args:
            pattern: String pattern to match against keys
        """
        keys_to_delete = [k for k in self.cache.keys() if pattern in k]
        for key in keys_to_delete:
            del self.cache[key]

    async def deduplicate_request(self, key: str, fetch_fn):
        """
        Deduplicate concurrent requests for the same resource

        If a request is already in flight, wait for it instead of duplicating.

        Args:
            key: Deduplication key
            fetch_fn: Async function to fetch data if not pending

        Returns:
            Result from fetch_fn or pending request
        """
        if key in self.pending_requests:
            # Another request is already fetching, wait for it
            return await self.pending_requests[key]

        # Create future for this request
        future = asyncio.Future()
        self.pending_requests[key] = future

        try:
            result = await fetch_fn()
            future.set_result(result)
            return result
        finally:
            # Remove from pending requests
            if key in self.pending_requests:
                del self.pending_requests[key]
