# Async Task Handling & Rate Limiting Design

**Status:** Design Document (Not Yet Implemented)
**Priority:** High Complexity - Major Architectural Change
**Estimated Effort:** 6-8 hours implementation
**Author:** Claude (AI Assistant)
**Date:** November 19, 2025

---

## Overview

This document outlines the design for implementing background task processing and rate limiting in Meridinate. These features will improve system scalability, prevent abuse, and enable better handling of long-running operations like token analysis.

---

## 1. Async Task Handling

### Problem Statement

Currently, token analysis runs synchronously in the FastAPI endpoint, causing:
- **Blocking requests:** Long analyses (30-60s) tie up worker threads
- **Timeout risks:** Browser/proxy timeouts on long requests
- **Poor scalability:** Limited concurrent analyses
- **No retry mechanism:** Failed analyses must be manually restarted

### Proposed Solution

Implement a task queue system using **arq** (async Redis queue) for Python async/await compatibility with FastAPI.

### Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   FastAPI   │────────▶│    Redis     │◀────────│  arq Worker │
│  (Web API)  │  Enqueue │   (Queue)    │  Dequeue│  (Processor)│
└─────────────┘         └──────────────┘         └─────────────┘
      │                                                  │
      │                                                  │
      ▼                                                  ▼
┌─────────────┐                                 ┌─────────────┐
│  WebSocket  │                                 │   Helius    │
│  (Updates)  │                                 │     API     │
└─────────────┘                                 └─────────────┘
```

### Implementation Plan

#### 1.1 Install Dependencies

```bash
cd apps/backend
pip install arq redis
```

#### 1.2 Create Task Worker (`src/meridinate/workers/analysis_worker.py`)

```python
"""
Analysis task worker using arq for async background processing
"""
import asyncio
from arq import create_pool
from arq.connections import RedisSettings
from meridinate.helius_api import TokenAnalyzer
from meridinate.settings import HELIUS_API_KEY, REDIS_URL
from meridinate import analyzed_tokens_db as db

async def analyze_token_task(ctx, job_id: str, token_address: str, settings: dict):
    """
    Background task for token analysis

    Args:
        ctx: arq context (provides Redis connection)
        job_id: Unique job identifier
        token_address: Token mint address to analyze
        settings: Analysis settings (min_usd, max_credits, etc.)
    """
    try:
        # Update job status to processing
        await ctx['redis'].set(f"job:{job_id}:status", "processing")

        # Run analysis
        analyzer = TokenAnalyzer(HELIUS_API_KEY)
        result = analyzer.analyze_token(
            mint_address=token_address,
            min_usd=settings.get('min_usd', 50.0),
            max_credits=settings.get('max_credits', 1000),
            max_wallets_to_store=settings.get('max_wallets', 10)
        )

        # Store results in database
        db.save_analysis_results(job_id, result)

        # Update job status to completed
        await ctx['redis'].set(f"job:{job_id}:status", "completed")
        await ctx['redis'].set(f"job:{job_id}:result", json.dumps(result))

        # Send WebSocket notification
        # (implementation depends on WebSocket manager)

        return {"status": "completed", "wallets_found": len(result['early_bidders'])}

    except Exception as e:
        # Update job status to failed
        await ctx['redis'].set(f"job:{job_id}:status", "failed")
        await ctx['redis'].set(f"job:{job_id}:error", str(e))
        raise


class WorkerSettings:
    """arq worker configuration"""

    functions = [analyze_token_task]
    redis_settings = RedisSettings.from_dsn(REDIS_URL or "redis://localhost:6379")

    # Retry configuration
    max_tries = 3
    retry_jobs = True

    # Job timeout (10 minutes for token analysis)
    job_timeout = 600

    # Worker settings
    max_jobs = 5  # Max concurrent analysis jobs
    poll_delay = 0.5  # Check for new jobs every 500ms
```

#### 1.3 Update Analysis Router (`src/meridinate/routers/analysis.py`)

```python
from arq import create_pool
from arq.connections import RedisSettings

# Create Redis pool for job enqueueing
redis_pool = None

@router.on_event("startup")
async def startup():
    global redis_pool
    redis_pool = await create_pool(RedisSettings.from_dsn(REDIS_URL))

@router.on_event("shutdown")
async def shutdown():
    if redis_pool:
        await redis_pool.close()

@router.post("/api/analysis/queue")
async def queue_token_analysis(request: AnalyzeTokenRequest):
    """
    Queue a token for background analysis

    Returns immediately with job_id for status tracking
    """
    job_id = str(uuid.uuid4())

    # Enqueue the analysis job
    job = await redis_pool.enqueue_job(
        'analyze_token_task',
        job_id,
        request.token_address,
        {
            'min_usd': request.min_usd,
            'max_credits': request.max_credits,
            'max_wallets': request.max_wallets_to_store
        }
    )

    # Store job metadata
    set_analysis_job(job_id, {
        "job_id": job_id,
        "status": "queued",
        "token_address": request.token_address,
        "queued_at": datetime.now().isoformat(),
        "arq_job_id": job.job_id
    })

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Analysis queued successfully"
    }

@router.get("/api/analysis/{job_id}/status")
async def get_analysis_status(job_id: str):
    """Get real-time status of analysis job"""
    job = get_analysis_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get real-time status from Redis
    status = await redis_pool.get(f"job:{job_id}:status")
    if status:
        job['status'] = status.decode()

    return job
```

#### 1.4 Start Worker Process

```bash
# Development
arq meridinate.workers.analysis_worker.WorkerSettings

# Production (systemd service)
[Unit]
Description=Meridinate arq Worker
After=network.target redis.service

[Service]
Type=simple
User=meridinate
WorkingDirectory=/opt/meridinate/apps/backend
ExecStart=/opt/meridinate/apps/backend/.venv/bin/arq meridinate.workers.analysis_worker.WorkerSettings
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Benefits

- ✅ **Non-blocking:** API responds instantly with job ID
- ✅ **Scalable:** Add more workers for concurrent processing
- ✅ **Resilient:** Automatic retries on failure
- ✅ **Monitorable:** Job status tracking via Redis
- ✅ **Async-native:** Full async/await support with FastAPI

### Migration Path

1. Keep existing synchronous endpoint for backward compatibility
2. Add new `/api/analysis/queue` endpoint for async processing
3. Update frontend to use async endpoint with status polling
4. Deprecate sync endpoint after transition period

---

## 2. Rate Limiting

### Problem Statement

Current API has no rate limiting, allowing:
- **Resource exhaustion:** Unlimited concurrent requests
- **Cost overruns:** Unlimited Helius API credit usage
- **Abuse potential:** No protection against automated attacks
- **DDoS vulnerability:** No throttling on expensive endpoints

### Proposed Solution

Implement multi-tier rate limiting using **slowapi** (Flask-Limiter port for FastAPI).

### Rate Limit Strategy

```python
# Different limits for different endpoints
RATE_LIMITS = {
    # Analysis endpoints (expensive)
    "/api/analysis/queue": "5 per hour",
    "/api/tokens/refresh-market-cap": "30 per hour",

    # Wallet endpoints (moderate)
    "/api/wallets/*/refresh-balance": "60 per hour",

    # Read-only endpoints (permissive)
    "/api/tokens": "300 per hour",
    "/api/wallets/*": "300 per hour",

    # Metrics/health (unrestricted)
    "/metrics": "1000 per hour",
    "/metrics/health": "1000 per hour"
}
```

### Implementation Plan

#### 2.1 Install Dependencies

```bash
pip install slowapi redis
```

#### 2.2 Configure Rate Limiter (`src/meridinate/middleware/rate_limit.py`)

```python
"""
Rate limiting middleware for FastAPI
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Request
from redis import Redis

# Initialize Redis for distributed rate limiting
redis_client = Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Create limiter with Redis storage
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379",
    strategy="fixed-window",  # or "moving-window" for smoother limiting
    default_limits=["300 per hour"]  # Global default
)

def setup_rate_limiting(app: FastAPI):
    """Configure rate limiting for FastAPI app"""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    return app
```

#### 2.3 Apply to Routes

```python
# In routers/analysis.py
from meridinate.middleware.rate_limit import limiter

@router.post("/api/analysis/queue")
@limiter.limit("5 per hour")  # Strict limit for expensive operations
async def queue_token_analysis(request: Request, data: AnalyzeTokenRequest):
    # ... existing code ...
    pass

@router.get("/api/tokens")
@limiter.limit("300 per hour")  # Permissive for read-only
async def get_tokens(request: Request):
    # ... existing code ...
    pass
```

#### 2.4 Custom Rate Limit Key Functions

```python
# Rate limit by API key instead of IP (for authenticated users)
def get_api_key(request: Request) -> str:
    """Extract API key from request headers"""
    return request.headers.get("X-API-Key", get_remote_address(request))

# Apply to specific endpoints
@router.post("/api/analysis/queue")
@limiter.limit("10 per hour", key_func=get_api_key)
async def queue_token_analysis(request: Request, data: AnalyzeTokenRequest):
    pass
```

#### 2.5 Rate Limit Response Headers

```python
# Automatically adds headers to responses:
# X-RateLimit-Limit: 300
# X-RateLimit-Remaining: 295
# X-RateLimit-Reset: 1637097600
```

### Rate Limit Configuration Matrix

| Endpoint                          | Limit          | Window | Reasoning                    |
|-----------------------------------|----------------|--------|------------------------------|
| `POST /api/analysis/queue`        | 5              | 1h     | Very expensive (Helius API)  |
| `POST /api/tokens/refresh-mc`     | 30             | 1h     | Moderate cost (DexScreener)  |
| `POST /api/wallets/*/refresh`     | 60             | 1h     | Moderate cost (Helius RPC)   |
| `GET /api/tokens`                 | 300            | 1h     | Cached, low cost             |
| `GET /api/wallets/*`              | 300            | 1h     | Cached, low cost             |
| `GET /metrics*`                   | 1000           | 1h     | Internal monitoring          |
| Global default                    | 300            | 1h     | Reasonable for most APIs     |

### Benefits

- ✅ **Cost control:** Prevents API credit overruns
- ✅ **Fair usage:** Prevents single user from monopolizing resources
- ✅ **DDoS protection:** Throttles automated attacks
- ✅ **Redis-backed:** Distributed rate limiting across multiple workers
- ✅ **Informative:** Headers tell clients their remaining quota

---

## 3. Observability Integration

### Metrics to Track

Add to existing Prometheus metrics:

```python
# In meridinate/observability/metrics.py

# Rate limit metrics
self._rate_limit_hits = defaultdict(int)  # endpoint -> count
self._rate_limit_blocks = defaultdict(int)  # endpoint -> count

def record_rate_limit_hit(self, endpoint: str):
    with self._lock:
        self._rate_limit_hits[endpoint] += 1

def record_rate_limit_block(self, endpoint: str):
    with self._lock:
        self._rate_limit_blocks[endpoint] += 1

# Task queue metrics
self._tasks_queued = 0
self._tasks_completed = 0
self._tasks_failed = 0
self._task_queue_depth = 0

def record_task_queued(self):
    with self._lock:
        self._tasks_queued += 1
        self._task_queue_depth += 1

def record_task_completed(self):
    with self._lock:
        self._tasks_completed += 1
        self._task_queue_depth = max(0, self._task_queue_depth - 1)
```

---

## 4. Implementation Checklist

### Phase 1: Async Tasks (4-5 hours)

- [ ] Install Redis and arq
- [ ] Create `analysis_worker.py` with task definition
- [ ] Update `analysis.py` router with queue endpoint
- [ ] Add job status tracking endpoints
- [ ] Update frontend to use async API
- [ ] Test retry/failure scenarios
- [ ] Create systemd service for worker
- [ ] Document worker deployment

### Phase 2: Rate Limiting (2-3 hours)

- [ ] Install slowapi
- [ ] Create rate limiting middleware
- [ ] Apply limits to all endpoints
- [ ] Add custom key functions for authenticated users
- [ ] Test rate limit enforcement
- [ ] Add Prometheus metrics for rate limits
- [ ] Document rate limit strategy
- [ ] Add rate limit info to API docs

### Phase 3: Testing & Documentation (1-2 hours)

- [ ] Write integration tests for async tasks
- [ ] Write integration tests for rate limits
- [ ] Update API documentation
- [ ] Update deployment guides
- [ ] Add monitoring dashboards
- [ ] Performance testing under load

---

## 5. Deployment Considerations

### Redis Requirements

```yaml
# docker-compose.yml addition
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
  command: redis-server --appendonly yes

volumes:
  redis_data:
```

### Environment Variables

```bash
# .env additions
REDIS_URL=redis://localhost:6379
RATE_LIMIT_ENABLED=true
RATE_LIMIT_STRATEGY=moving-window
```

### Resource Requirements

- **Redis:** ~50MB RAM for queue/rate-limit storage
- **Worker:** ~200MB RAM per worker process
- **Recommended:** 1 worker per 2 CPU cores

---

## 6. Future Enhancements

- **Priority queues:** High-priority analysis for premium users
- **Scheduled tasks:** Periodic market cap refreshes
- **Task chaining:** Multi-step analysis workflows
- **Rate limit tiers:** Different limits for authenticated vs anonymous
- **Adaptive rate limiting:** Adjust limits based on system load
- **Cost-based limiting:** Limit by estimated API credits used

---

## Summary

This design provides a production-ready foundation for:
- **Scalable background processing** with arq
- **Fair resource allocation** with slowapi rate limiting
- **Better user experience** with non-blocking operations
- **Cost control** through usage limits

Implementation should be done in phases, with careful testing at each stage to ensure system stability.
