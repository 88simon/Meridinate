"""
Rate limiting middleware for FastAPI using slowapi

Provides tiered rate limiting for different endpoint categories:
- Analysis endpoints: Strict limits (expensive Helius API calls)
- Market cap refresh: Moderate limits (DexScreener rate limiting)
- Wallet balance refresh: Moderate limits (Helius RPC cost)
- Read-only endpoints: Permissive limits (cached data)
- Metrics/health: Unrestricted (internal monitoring)
"""

from fastapi import FastAPI, Request, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from meridinate.observability import log_info, metrics_collector
from meridinate.settings import RATE_LIMIT_ENABLED, REDIS_ENABLED, REDIS_URL


def get_client_identifier(request: Request) -> str:
    """
    Get client identifier for rate limiting

    Priority order:
    1. X-API-Key header (for authenticated users)
    2. X-Forwarded-For header (for proxied requests)
    3. Remote address (direct connections)
    """
    # Check for API key (future: implement API key authentication)
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"apikey:{api_key}"

    # Check for X-Forwarded-For (proxied requests)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain
        client_ip = forwarded_for.split(",")[0].strip()
        return f"ip:{client_ip}"

    # Fall back to remote address
    return f"ip:{get_remote_address(request)}"


# Initialize limiter
limiter = Limiter(
    key_func=get_client_identifier,
    storage_uri=REDIS_URL if REDIS_ENABLED else "memory://",  # Use Redis if available, otherwise in-memory
    strategy="fixed-window",  # Fixed-window strategy (simpler, more predictable)
    default_limits=["300 per hour"],  # Global default for unlisted endpoints
    enabled=RATE_LIMIT_ENABLED,  # Can be disabled via environment variable
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """
    Custom rate limit exceeded handler

    Logs the rate limit hit and tracks metrics
    Includes CORS headers for frontend compatibility
    """
    client_id = get_client_identifier(request)
    endpoint = request.url.path

    # Track metrics
    metrics_collector.record_rate_limit_block(endpoint)

    # Log the rate limit hit
    log_info(
        "Rate limit exceeded",
        client_id=client_id,
        endpoint=endpoint,
        limit=exc.detail,
    )

    # Return standard rate limit response with CORS headers
    return Response(
        content=f"Rate limit exceeded: {exc.detail}",
        status_code=429,
        headers={
            "Retry-After": str(exc.detail),
            "X-RateLimit-Limit": str(exc.detail),
            # CORS headers for frontend compatibility
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )


def setup_rate_limiting(app: FastAPI) -> FastAPI:
    """
    Configure rate limiting for FastAPI app

    Args:
        app: FastAPI application instance

    Returns:
        FastAPI app with rate limiting configured
    """
    if not RATE_LIMIT_ENABLED:
        log_info("Rate limiting disabled (RATE_LIMIT_ENABLED=false)")
        return app

    # Attach limiter to app state
    app.state.limiter = limiter

    # Add custom exception handler
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    log_info(
        "Rate limiting enabled",
        storage=REDIS_URL if REDIS_ENABLED else "memory",
        strategy="fixed-window",
        default_limit="300 per hour",
    )

    return app


# Rate limit constants for common endpoints
ANALYSIS_RATE_LIMIT = "20 per hour"  # Strict - expensive Helius API calls
MARKET_CAP_RATE_LIMIT = "30 per hour"  # Moderate - DexScreener rate limits
WALLET_BALANCE_RATE_LIMIT = "60 per hour"  # Moderate - Helius RPC cost
READ_RATE_LIMIT = "300 per hour"  # Permissive - cached data
METRICS_RATE_LIMIT = "1000 per hour"  # Unrestricted - internal monitoring


def conditional_rate_limit(rate_limit_string: str):
    """
    Conditional rate limit decorator that only applies when RATE_LIMIT_ENABLED=true

    When disabled, returns a no-op decorator that doesn't interfere with the endpoint
    """
    def decorator(func):
        if not RATE_LIMIT_ENABLED:
            # When disabled, just return the original function unchanged
            return func

        # When enabled, apply the actual limiter decorator
        return limiter.limit(rate_limit_string)(func)

    return decorator
