# Meridinate Backend

FastAPI-based backend service for Solana token analysis with async task processing, rate limiting, and real-time WebSocket notifications.

## Architecture

**Unified FastAPI Application** - Single service combining REST API, WebSocket notifications, and async task processing:

- **FastAPI REST API** (port 5003) - Token analysis, wallet management, market cap tracking
- **WebSocket Server** (port 5003/ws) - Real-time analysis notifications
- **Async Task Queue** (arq + Redis) - Background task processing for long-running operations
- **Rate Limiting** (slowapi) - Configurable endpoint protection with conditional disabling
- **Helius Integration** (`helius_api.py`) - Solana blockchain data and token analysis
- **SQLite Database** (`analyzed_tokens.db`) - Persistent storage with 7 tables: tokens, wallets, analysis runs, wallet tags, token tags, wallet activity, and multi-token metadata

## Requirements

- **Python 3.11+**
- **pip** and virtual environment
- **Helius API key** for token analysis and blockchain data
- **Redis** (optional) - Required for distributed deployments or async task persistence
- **DexScreener API** (free, no key) - Market cap data with 60 requests/minute rate limit
- **CoinGecko API** (free, no key) - Real-time SOL/USD price data

## Installation

> **Important:** Develop outside of OneDrive to avoid shell extension conflicts with `node_modules` and Python virtual environments.

```bash
cd apps/backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

## Configuration

### Required Configuration Files

1. **config.json** - API credentials and analysis settings
   ```json
   {
     "helius_api_key": "YOUR_HELIUS_KEY",
     "default_threshold": 100,
     "analysis_min_usd": 50
   }
   ```

2. **api_settings.json** - Runtime API settings (auto-created)
   ```json
   {
     "walletCount": 5,
     "concurrentAnalysis": 3,
     "apiRateDelay": 0.2,
     "maxCreditsPerAnalysis": 500
   }
   ```

3. **monitored_addresses.json** - Wallet watchlist (auto-created)
   ```json
   []
   ```

### Environment Variables

Override configuration with environment variables:

```bash
# API Keys
HELIUS_API_KEY=your_key_here

# Server Configuration
HOST=0.0.0.0
PORT=5003
DEBUG=false

# Rate Limiting
RATE_LIMIT_ENABLED=true        # Enable/disable rate limiting
RATE_LIMIT_STORAGE_URI=memory  # 'memory' or Redis URI

# Redis Configuration (optional)
REDIS_ENABLED=false
REDIS_HOST=localhost
REDIS_PORT=6379

# Analysis Settings
DEFAULT_THRESHOLD=100
ANALYSIS_MIN_USD=50
API_RATE_DELAY=0.2
```

## Running the Service

### From Monorepo Root

**Windows:**
```cmd
scripts\start-backend.bat
```

**macOS/Linux:**
```bash
chmod +x scripts/start-backend.sh
./scripts/start-backend.sh
```

### Manual Start

```bash
cd apps/backend/src
python -m meridinate.main
```

The service starts on **http://localhost:5003** with:
- REST API endpoints
- WebSocket at `ws://localhost:5003/ws`
- Interactive API docs at http://localhost:5003/docs
- Health check at http://localhost:5003/health

## API Overview

### Token Analysis

| Method | Route | Purpose | Rate Limit |
| --- | --- | --- | --- |
| `GET` | `/api/tokens/history` | List analyzed tokens | - |
| `GET` | `/api/tokens/{id}` | Get token details | - |
| `GET` | `/api/tokens/{id}/history` | Token analysis history | - |
| `DELETE` | `/api/tokens/{id}` | Soft-delete token | - |
| `POST` | `/api/tokens/{id}/restore` | Restore deleted token | - |
| `DELETE` | `/api/tokens/{id}/permanent` | Permanently delete | - |
| `POST` | `/api/tokens/refresh-market-caps` | Refresh market caps (batch) | 30/hour |
| `GET` | `/api/tokens/trash` | List deleted tokens | - |
| `POST` | `/api/analysis` | Start new analysis job | 20/hour |
| `GET` | `/api/tokens/{id}/tags` | Get token tags (GEM/DUD) | - |
| `POST` | `/api/tokens/{id}/tags` | Add tag to token | - |
| `DELETE` | `/api/tokens/{id}/tags` | Remove tag from token | - |
| `GET` | `/api/tokens/{mint_address}/top-holders` | Get top N token holders with USD balances (N: 5-20, default 10) | 30/hour |

### Wallet Management

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/wallets/{address}` | Get wallet details |
| `GET` | `/api/multitokens/wallets` | Get multi-token wallets with NEW indicators |
| `POST` | `/wallets/refresh-balances` | Refresh wallet balances (batch) |
| `GET` | `/wallets/{address}/tags` | Get wallet tags |
| `POST` | `/wallets/{address}/tags` | Add tag to wallet |
| `DELETE` | `/wallets/{address}/tags` | Remove tag from wallet |
| `POST` | `/wallets/batch-tags` | Get tags for multiple wallets |
| `GET` | `/wallets/{address}/top-holder-tokens` | Get all tokens where wallet is a top holder (full data) |
| `POST` | `/wallets/batch-top-holder-counts` | Get top holder counts for multiple wallets (optimized) |

**Multi-Token Early Wallets Features:**
- Returns wallets appearing in 2+ analyzed tokens
- Includes `is_new` boolean flag for newly added wallets
- Includes `marked_at_analysis_id` to identify which token caused multi-token status
- Tracks NEW status in `multi_token_wallet_metadata` table
- NEW flags cleared on next analysis completion

**Top Holders Feature:**
- Configurable limit: 5-20 holders (default: 10, aligned with Helius API cap)
- Automatically fetched during token analysis (non-blocking)
- Resolves token account addresses to wallet owner addresses
- Filters out program-derived addresses (only on-curve wallets)
- Calculates token balance in USD using DexScreener price API
- Fetches total wallet balance in USD via Helius API
- Stored in database as JSON with timestamp (`top_holders_json`, `top_holders_updated_at`)
- Manual refresh updates data and adds credits to cumulative total
- API Credits: 11-21 credits per fetch (varies based on caching)
- Default setting now included in `DEFAULT_API_SETTINGS` for cold start compatibility

**Wallet Top Holders Optimization:**
- `POST /wallets/batch-top-holder-counts` - Returns only counts for badge display
- 98% bandwidth reduction vs individual lookups (50 requests to 1, 3000 records to 50 numbers)
- 5-minute cache to prevent hot-looping on scroll
- Client-side refetch callbacks for instant updates without page reload

### Watchlist

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/watchlist/register` | Add wallet to watchlist |
| `GET` | `/watchlist/addresses` | List monitored wallets |
| `GET` | `/watchlist/address/{address}` | Get watchlist entry |
| `PUT` | `/watchlist/address/{address}/note` | Update wallet note |
| `DELETE` | `/watchlist/address/{address}` | Remove from watchlist |
| `POST` | `/watchlist/import` | Bulk import wallets |
| `POST` | `/watchlist/clear` | Clear all watchlist entries |

### SWAB (Smart Wallet Archive Builder)

Position tracking system for Multi-Token Early Wallets (MTEWs).

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/swab/positions` | List tracked positions with filters |
| `GET` | `/api/swab/settings` | Get SWAB configuration |
| `POST` | `/api/swab/settings` | Update SWAB configuration |
| `POST` | `/api/swab/check` | Trigger manual position check |
| `POST` | `/api/swab/update-pnl` | Update PnL for all positions |
| `POST` | `/api/swab/purge` | Clear all SWAB data |
| `POST` | `/api/swab/positions/{id}/untrack` | Stop tracking a position |
| `POST` | `/api/swab/reconcile/{token_id}` | Reconcile sold positions for a token |
| `POST` | `/api/swab/reconcile-all` | Batch reconcile all sold positions |

**Key Features:**
- **MTEW Gate:** Configurable threshold (1-10) for which MTEWs get tracked
- **Position Detection:** Monitors balance changes to detect buys/sells
- **Webhook-First Sell Detection:** Real-time sell capture via Helius webhooks
- **PnL Calculation:** Actual `exit_price / entry_price` for sold positions
- **FPnL (Fumbled PnL):** Shows missed opportunity for sold positions (`current_mc / entry_mc`)
- **Position Reconciliation:** Manual tool to fix sold positions missing sell data (pre-webhook sales)

**Position Reconciliation:**
- Finds positions where `total_sold_usd = 0` or `sell_count = 0`
- Looks up historical transactions via Helius API to find actual sell data
- Updates position with accurate USD received and recalculates PnL
- **Limitation:** Active traders may have 50+ transactions, causing old sells to scroll out of queryable history (~100 tx window)
- When transaction lookup fails, USD is estimated from current DexScreener price
- Query parameters: `max_signatures` (10-200, default 50), `max_positions` (for batch endpoint)

### Webhooks

Real-time transaction monitoring via Helius webhooks.

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/webhooks/create` | Create webhook for token wallets |
| `POST` | `/webhooks/create-swab` | Create webhook for all active SWAB wallets |
| `GET` | `/webhooks/list` | List all active webhooks |
| `GET` | `/webhooks/{webhook_id}` | Get webhook details |
| `DELETE` | `/webhooks/{webhook_id}` | Delete a webhook |
| `POST` | `/webhooks/callback` | Receive Helius webhook notifications |

**SWAB Integration:**
- **SELL Detection**: When tracked wallet sends tokens (`fromUserAccount`), captures exit price
- **BUY/DCA Detection**: When tracked wallet receives tokens (`toUserAccount`), updates cost basis
- **RE-ENTRY Detection**: When a sold position buys again, reactivates position and records buy
- Gets current price from DexScreener (real-time, accurate)
- This webhook-first approach captures accurate prices before transactions scroll out of history

**Setup for Production:**
1. Webhook callback URL must be publicly accessible
2. Use ngrok or similar for local testing: `ngrok http 5003`
3. Create webhook for all SWAB wallets via `POST /webhooks/create-swab` with your public callback URL:
   ```bash
   curl -X POST http://localhost:5003/webhooks/create-swab \
     -H "Content-Type: application/json" \
     -d '{"webhook_url": "https://your-public-url.ngrok.io/webhooks/callback"}'
   ```
4. Webhooks monitor `TRANSFER` and `SWAP` transaction types
5. The webhook will be created for all wallets with active (still holding) SWAB positions

### Tags & Codex

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/tags` | List all unique tags |
| `GET` | `/tags/{tag}/wallets` | Get wallets with specific tag |
| `GET` | `/codex` | Get wallet directory (all tagged wallets) |

### Settings & Health

| Method | Route | Purpose |
| --- | --- | --- |
| `GET/POST` | `/api/settings` | Backend analysis settings |
| `GET/POST` | `/api/solscan-settings` | Solscan URL parameters |
| `GET` | `/health` | Service health check |
| `GET` | `/metrics` | Observability metrics (Prometheus format) |

## Async Task Processing

The backend uses **arq** (asyncio task queue) with Redis for handling long-running operations:

### Features

- **Background Processing** - Offload expensive operations (token analysis, market cap refresh)
- **Configurable Storage** - In-memory (development) or Redis (production)
- **Graceful Degradation** - Falls back to sync processing if Redis unavailable
- **Queue Monitoring** - Health checks and metrics for task queue status

### Configuration

```python
# In meridinate/settings.py
REDIS_ENABLED = False  # Set to True for production
REDIS_HOST = "localhost"
REDIS_PORT = 6379

# Queue configuration
ARQ_QUEUE_NAME = "meridinate:queue"
ARQ_MAX_JOBS = 100
ARQ_JOB_TIMEOUT = 600  # 10 minutes
```

### Task Types

1. **Token Analysis** (`analyze_token_task`)
   - Fetches early bidders for Solana tokens
   - Processes transaction history
   - Stores results in database

2. **Market Cap Refresh** (`refresh_market_cap_task`)
   - Updates token market caps from DexScreener/Helius
   - Batch processing with rate limit handling

3. **Wallet Balance Refresh** (`refresh_wallet_balance_task`)
   - Updates wallet SOL balances with USD values
   - Real-time SOL price from CoinGecko (5-min cache)

## Rate Limiting

The backend uses **slowapi** for endpoint rate limiting:

### Configuration

Rate limiting can be **enabled/disabled globally** via environment variable:

```bash
RATE_LIMIT_ENABLED=true   # Enable rate limiting
RATE_LIMIT_ENABLED=false  # Disable rate limiting (development/testing)
```

### Storage Options

```bash
# In-memory storage (single instance, development)
RATE_LIMIT_STORAGE_URI=memory

# Redis storage (distributed, production)
RATE_LIMIT_STORAGE_URI=redis://localhost:6379
```

### Rate Limits

- **Analysis Endpoints:** 20 requests/hour per client
- **Market Cap Refresh:** 30 requests/hour per client
- **General Endpoints:** No limit

### Client Identification

Clients are identified by:
1. **API Key** (if provided via X-API-Key header) - highest priority
2. **X-Forwarded-For** header (behind proxy)
3. **Client IP address** (direct connection)

### Conditional Decorator

The `conditional_rate_limit` decorator only applies rate limiting when enabled:

```python
from meridinate.middleware.rate_limit import conditional_rate_limit, ANALYSIS_RATE_LIMIT

@router.post("/analyze")
@conditional_rate_limit(ANALYSIS_RATE_LIMIT)  # "20 per hour"
async def analyze_token(request: Request, data: AnalyzeRequest):
    # Only rate limited if RATE_LIMIT_ENABLED=true
    pass
```

## WebSocket Notifications

Real-time notifications for analysis completion:

### Connection

```javascript
const ws = new WebSocket('ws://localhost:5003/ws');

ws.onmessage = (event) => {
  const notification = JSON.parse(event.data);
  console.log('Analysis complete:', notification);
};
```

### Event Types

**analysis_complete:**
```json
{
  "event": "analysis_complete",
  "data": {
    "token_id": 42,
    "token_name": "Example Token",
    "token_symbol": "EXMPL",
    "acronym": "EXMPL",
    "wallets_found": 12,
    "analysis_time": "2025-01-20T10:30:00Z"
  }
}
```

### Resource Management

- **Auto-cleanup:** Connections close after 30s of tab inactivity
- **Smart reconnection:** Only when tab is visible, with linear backoff
- **Max retries:** 5 failed attempts before stopping

## Market Cap Refresh

Dual-source strategy for real-time market cap updates:

### Primary Source: DexScreener API

- **Free, no API key required**
- Excellent coverage for pump.fun and DEX-traded tokens
- Rate limit: 60 requests/minute per IP
- Returns HTTP 429 when rate limited
- No API credits consumed

### Fallback Source: Helius DAS API

- **Requires API key**
- Covers top 10k tokens by 24h trading volume
- Consumes 1 API credit per request
- Used only when DexScreener returns no data

### Usage

```bash
POST /api/tokens/refresh-market-caps
Content-Type: application/json

{
  "token_ids": [1, 2, 3, 4, 5]
}
```

### Response

```json
{
  "status": "success",
  "message": "Refreshed 5/5 token market caps",
  "results": [
    {
      "token_id": 1,
      "success": true,
      "market_cap_usd": 125000.50,
      "updated_at": "2025-01-20T10:30:00Z",
      "source": "dexscreener"
    }
  ],
  "total_tokens": 5,
  "successful": 5,
  "failed": 0,
  "credits_used": 0
}
```

## Wallet Balance Refresh

Real-time wallet balance updates with accurate SOL/USD pricing:

### SOL Price Integration

- **CoinGecko API** (free, no key required)
- Real-time SOL/USD price fetching
- 5-minute cache to minimize API calls
- Fallback to $100 if CoinGecko unavailable

### Balance Calculation

- Uses Helius `getBalance` RPC call
- Converts: `(lamports / 1,000,000,000) * sol_price_usd`
- Consumes 1 API credit per wallet
- Updates `wallet_balance_usd` in database

### Usage

```bash
POST /wallets/refresh-balances
Content-Type: application/json

{
  "wallet_addresses": ["address1...", "address2..."]
}
```

## Data Storage

### Database Files

- **analyzed_tokens.db** - SQLite database for tokens, wallets, tags
  - `analyzed_tokens` table: token data with market caps
  - `wallet_tags` table: wallet tagging system
  - `analysis_history` table: historical analysis runs

### JSON Files (gitignored)

- **monitored_addresses.json** - Wallet watchlist
- **api_settings.json** - Runtime API settings
- **config.json** - API credentials and configuration

### Analysis Outputs

- **data/analysis_results/** - JSON analysis outputs per token
- **data/axiom_exports/** - Axiom-formatted data exports
- **data/backups/** - Database backups with manifests

### Market Cap Fields

Each token has dual market cap tracking:
- `market_cap_usd`: Original market cap at analysis time
- `market_cap_usd_current`: Latest refreshed value
- `market_cap_updated_at`: Timestamp of last refresh
- `market_cap_ath`: All-time high market cap

### Top 10 Holders Fields

Each token stores top holders data:
- `top_holders_json`: JSON array of top 10 wallet holders with balances
- `top_holders_updated_at`: Timestamp of last fetch/refresh

Structure of `top_holders_json`:
```json
[
  {
    "address": "wallet_owner_address",
    "amount": "raw_token_balance",
    "decimals": 9,
    "uiAmountString": "human_readable_balance",
    "token_balance_usd": 1234.56,
    "wallet_balance_usd": 98765.43
  }
]
```

## Testing

### Run All Tests

```bash
# Set PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# Run pytest
pytest tests/ -v --cov=meridinate

# Run with coverage report
pytest tests/ -v --cov=meridinate --cov-report=html
```

### Test Configuration

Tests run with:
- `RATE_LIMIT_ENABLED=false` - Disable rate limiting
- `REDIS_ENABLED=false` - Use in-memory storage
- Temporary SQLite database per test
- Mock Helius API responses

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── middleware/
│   └── test_rate_limit.py   # Rate limiting tests
├── routers/
│   ├── test_tokens.py       # Token API tests
│   ├── test_wallets.py      # Wallet API tests
│   └── test_tags.py         # Tagging system tests
├── services/
│   └── test_watchlist_service.py
└── utils/
    └── test_validators.py
```

## Observability

### Structured Logging

```python
from meridinate.observability.structured_logger import get_logger

logger = get_logger(__name__)
logger.info("Analysis completed", extra={
    "token_id": 42,
    "wallets_found": 12,
    "duration_ms": 1500
})
```

### Metrics Endpoint

Prometheus-compatible metrics at `/metrics`:

```
# Request counts
meridinate_requests_total{method="POST",endpoint="/api/analysis"}
meridinate_requests_in_progress{method="POST",endpoint="/api/analysis"}

# Response times
meridinate_request_duration_seconds{method="POST",endpoint="/api/analysis"}

# Business metrics
meridinate_analysis_jobs_total
meridinate_tokens_analyzed_total
meridinate_helius_credits_used_total
```

## Troubleshooting

### Common Issues

**Missing dependencies:**
```bash
pip install -r requirements.txt
```

**Port already in use:**
```bash
# Change port in environment
export PORT=5004
python -m meridinate.main
```

**Helius quota exceeded:**
- Adjust `apiRateDelay` in `api_settings.json`
- Lower `maxCreditsPerAnalysis`
- Get additional API credits

**DexScreener rate limit (HTTP 429):**
- Wait ~1 minute before retrying
- Reduce batch size for market cap refreshes
- 60 requests/minute limit resets on rolling window

**Redis connection failed:**
- Set `REDIS_ENABLED=false` for local development
- Falls back to in-memory storage automatically

**WebSocket not connecting:**
- Check firewall allows port 5003
- Verify service is running: `curl http://localhost:5003/health`
- Check browser console for connection errors

### Debug Mode

Enable verbose logging:

```python
# In meridinate/settings.py
DEBUG = True
LOG_LEVEL = "DEBUG"
```

## CI/CD

GitHub Actions workflow (`../.github/workflows/monorepo-ci.yml`):

- **Backend Tests** - Runs pytest with coverage
- **Dependency Verification** - Ensures arq, redis, slowapi installed
- **API Schema Generation** - Validates OpenAPI schema
- **Type Checking** - MyPy static analysis (future)

## Security

- **API Keys** - Stored in `config.json` (gitignored)
- **Input Validation** - Pydantic models for all endpoints
- **Rate Limiting** - Prevents abuse when enabled
- **CORS** - Configured for frontend origin
- **No Secrets in Logs** - Structured logger filters sensitive data

See `docs/security/SECURITY.md` for complete security guidelines.

## Development

### Project Structure

```
apps/backend/
├── src/meridinate/          # Main package
│   ├── main.py              # FastAPI app entry
│   ├── routers/             # API endpoints
│   ├── services/            # Business logic
│   ├── middleware/          # Rate limiting, logging
│   ├── observability/       # Metrics, structured logging
│   ├── utils/               # Shared utilities
│   ├── settings.py          # Configuration
│   ├── state.py             # Application state
│   ├── helius_api.py        # Helius integration
│   ├── analyzed_tokens_db.py # Database operations
│   └── cache.py             # Response caching
├── tests/                   # Test suite
├── data/                    # Data files (gitignored)
├── logs/                    # Log files (gitignored)
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

### Code Style

- **Formatter:** Black (line length: 120)
- **Linter:** Flake8
- **Type Checker:** MyPy (future)
- **Docstrings:** Google style

### Adding New Endpoints

1. Create router in `src/meridinate/routers/`
2. Add Pydantic models in `utils/models.py`
3. Implement business logic in `services/`
4. Add tests in `tests/routers/`
5. Update OpenAPI schema: `pnpm sync-types:update` (from frontend)

## License

MIT License - See LICENSE file for details.

---

**Questions or issues?** Check `docs/` or open a GitHub issue.
