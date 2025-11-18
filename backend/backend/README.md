# Gun Del Sol Backend

This folder hosts every backend service that powers the Gun Del Sol action wheel:

- **Flask REST API (`api_service.py`, port 5001)** for watchlists, token analysis, CSV exports, and API settings.
- **FastAPI WebSocket server (`websocket_server.py`, port 5002)** for real-time `analysis_start` and `analysis_complete` notifications.
- **Helius integration (`helius_api.py`)** plus persistence helpers (`analyzed_tokens_db.py`, `secure_logging.py`, `debug_config.py`).

## Requirements

- Python 3.9 or later
- pip and a virtual environment (recommended)
- Valid Helius API key if you intend to run token analysis
- DexScreener API (free, no API key required) for market cap data with 60 requests/minute rate limit
- CoinGecko API (free, no API key required) for real-time SOL/USD price data
- Redis is optional but recommended later if you distribute Socket.IO or WebSocket broadcasts

## Installation

> **Important:** Develop outside of OneDrive to avoid shell extension conflicts with `node_modules` and Python virtual environments.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The root `start_backend.bat` script automatically detects and activates the virtual environment at `backend\.venv\` if it exists, falling back to global Python if not found.

## Configuration

1. Copy `config.example.json` to `config.json`.
2. Set at minimum:
   ```json
   {
     "helius_api_key": "YOUR_KEY",
     "default_threshold": 100,
     "analysis_min_usd": 50
   }
   ```
3. Override any value via environment variables when needed:
   - `HELIUS_API_KEY`
   - `API_RATE_DELAY`
   - `DEFAULT_THRESHOLD`

The Flask service also persists user-tunable API settings to `api_settings.json`; you can edit the file or call `POST /api/settings`.

## Running the Services

### From the repository root

```powershell
start_backend.bat
```

The script launches:
- Flask REST API on http://localhost:5001
- FastAPI WebSocket server on http://localhost:5002

### Manual control

```powershell
python api_service.py          # Flask REST API
python websocket_server.py     # FastAPI WebSocket server
```

Both scripts auto-reload when `debug_config.py` enables debug mode.

## REST API Overview

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/register` | Add a wallet to the monitoring list |
| `GET` | `/addresses` | List known wallets |
| `GET` | `/address/<address>` | Fetch a single wallet record |
| `PUT` | `/address/<address>/note` | Update a note/tag |
| `DELETE` | `/address/<address>` | Remove a wallet |
| `POST` | `/import` | Bulk import watchlist entries |
| `POST` | `/clear` | Delete every watchlist entry |
| `GET` | `/analysis` | List analysis jobs |
| `POST` | `/analysis` | Queue a new analysis job |
| `GET` | `/analysis/<job_id>` | Poll job status/results |
| `GET` | `/analysis/<job_id>/results` | Render results as HTML |
| `GET` | `/analysis/<job_id>/csv` | Download CSV |
| `GET` | `/api/tokens/<token_id>` | Inspect a stored token |
| `GET` | `/api/tokens/<token_id>/history` | Show historical runs |
| `DELETE` | `/api/tokens/<token_id>` | Soft-delete a token |
| `POST` | `/api/tokens/<token_id>/restore` | Restore from trash |
| `DELETE` | `/api/tokens/<token_id>/permanent` | Hard-delete |
| `POST` | `/api/tokens/refresh-market-caps` | Refresh current market caps for multiple tokens |
| `POST` | `/wallets/refresh-balances` | Refresh wallet balances for multiple wallets |
| `GET/POST` | `/api/settings` | Read or update backend analysis defaults |
| `GET/POST` | `/api/solscan-settings` | Read or update Solscan URL parameters for action wheel |
| `GET` | `/health` | Service heartbeat for launch scripts |

All responses are JSON except for the HTML and CSV exports.

## WebSocket Notifications

- Clients connect to `ws://localhost:5002/ws`.
- The Flask service posts to `/notify/analysis_start` and `/notify/analysis_complete` whenever a job transitions states.
- Sample payload:
  ```json
  {
    "event": "analysis_complete",
    "data": {
      "job_id": "b2b1de34",
      "token_name": "Example",
      "token_symbol": "EXMPL",
      "acronym": "EXMPL",
      "wallets_found": 12,
      "token_id": 42
    }
  }
  ```
- The `/health` route on the FastAPI server reports active WebSocket connections for monitoring.

## Data Storage

- `monitored_addresses.json`: primary watchlist (JSON, git-ignored)
- `analysis_results/` and `axiom_exports/`: per-job outputs and exports
- `analyzed_tokens.db` / `solscan_monitor.db`: SQLite databases holding aggregated results
- `api_settings.json`: persisted API defaults
- `action_wheel_settings.ini`: Solscan URL parameters and action wheel configuration (UTF-16 encoded)

The `analyzed_tokens` table includes two market cap fields:
- `market_cap_usd`: original market cap at time of analysis
- `market_cap_usd_current`: refreshed market cap from latest API call
- `market_cap_updated_at`: timestamp of last refresh

Back up these files before reinstalling or switching machines. All sensitive paths stay on disk only; `SECURITY.md` covers safe handling.

## Market Cap Refresh Feature

The backend provides real-time market cap updates using a dual-source strategy:

1. **Primary Source - DexScreener API** (free, no API key required)
   - Excellent coverage for pump.fun and DEX-traded tokens
   - Rate limit: 60 requests/minute per IP
   - Returns HTTP 429 when rate limited
   - No API credits consumed

2. **Fallback Source - Helius DAS API** (requires API key)
   - Covers top 10k tokens by 24h trading volume
   - Consumes 1 API credit per request
   - Used only when DexScreener returns no data

**Usage:**
```bash
POST /api/tokens/refresh-market-caps
Content-Type: application/json

{
  "token_ids": [1, 2, 3]
}
```

**Response includes:**
- Individual results per token with success status
- Updated market cap values and timestamps
- Total API credits consumed (Helius only)

**Rate Limiting:**
To avoid DexScreener rate limits when refreshing multiple tokens, the endpoint processes requests sequentially with appropriate delays. If you hit the 60/minute limit, wait ~1 minute before retrying.

## Wallet Balance Refresh Feature

The backend provides real-time wallet balance updates with accurate SOL/USD pricing:

1. **SOL Price Integration** (CoinGecko API - free, no API key required)
   - Real-time SOL/USD price fetching
   - 5-minute cache to minimize external API calls
   - Fallback to $100 if CoinGecko unavailable
   - No API credits consumed for price fetching

2. **Balance Calculation** (Helius RPC API)
   - Uses `getBalance` RPC call to fetch lamports
   - Converts: `(lamports / 1,000,000,000) * sol_price_usd`
   - Consumes 1 API credit per wallet balance request
   - Updates `wallet_balance_usd` in database

**Usage:**
```bash
POST /wallets/refresh-balances
Content-Type: application/json

{
  "wallet_addresses": ["address1...", "address2..."]
}
```

**Response includes:**
- Individual results per wallet with success status
- Updated balance values in USD
- Total API credits consumed (1 per successful wallet)
- Success count vs total wallets

**Implementation:**
The wallet balance refresh uses the same `HeliusAPI.get_wallet_balance()` method across all endpoints to ensure consistency. This method fetches real-time SOL price from CoinGecko (cached for 5 minutes) and combines it with lamport balance from Helius RPC to calculate accurate USD values.

## Solscan Settings Management

The backend provides centralized management of Solscan URL parameters that integrate with the AutoHotkey action wheel:

**Features:**
- Web UI-controlled settings panel for Solscan parameters
- Auto-save to `action_wheel_settings.ini` (UTF-16 encoded)
- Dynamic URL generation for multi-token wallet hyperlinks
- AHK action wheel reads settings on each use

**Settings:**
- `activity_type`: Filter by transaction type (SPL Transfer, SOL Transfer, etc.)
- `exclude_amount_zero`: Exclude zero-amount transactions
- `remove_spam`: Filter out spam transactions
- `value`: Minimum transaction value filter
- `token_address`: Filter by specific token address
- `page_size`: Number of transactions per page (10, 20, 30, 40, 60, 100)

**Usage:**
```bash
# Get current settings
GET /api/solscan-settings

# Update settings
POST /api/solscan-settings
Content-Type: application/json

{
  "activity_type": "ACTIVITY_SPL_TRANSFER",
  "value": "200",
  "page_size": "20"
}
```

**Response:**
```json
{
  "status": "success",
  "settings": {
    "activity_type": "ACTIVITY_SPL_TRANSFER",
    "exclude_amount_zero": "true",
    "remove_spam": "true",
    "value": "200",
    "token_address": "So11111111111111111111111111111111111111111",
    "page_size": "20"
  }
}
```

**Integration:**
- Frontend settings modal provides dropdown controls for all parameters
- Auto-save after 300ms of changes
- Multi-token wallet hyperlinks update dynamically via 500ms polling
- AHK action wheel reads from INI file on each Solscan wedge invocation

**File Storage:**
Settings are persisted to `action_wheel_settings.ini` with UTF-16-LE encoding in the `[Solscan]` section.

## Logging & Debugging

- `secure_logging.py` centralizes safe log helpers (`log_info`, `log_success`, etc.).
- `debug_config.py` toggles verbose logging globally; ensure production mode keeps it disabled.
- When diagnosing issues, run the services manually so you can read stack traces directly in the console.

## Troubleshooting

- **Missing dependencies:** re-run `python -m pip install -r requirements.txt`.
- **Port already in use:** edit the host/port passed to `socketio.run` (Flask) or `uvicorn.run` (FastAPI).
- **Helius quota exceeded:** throttle via `api_settings.json` (`apiRateDelay`, `maxCreditsPerAnalysis`) or set a new API key.
- **DexScreener rate limit (HTTP 429):** wait ~1 minute before retrying market cap refreshes; the 60 requests/minute limit resets on a rolling window.
- **Market cap returns null:** token may be too new/small for DexScreener; fallback to Helius will be attempted (consumes 1 credit).
- **WebSocket broadcasts never arrive:** confirm `websocket_server.py` is running and that `api_service.py` reports successful POSTs to `/notify/...`.

The backend is intentionally modular—extend it with new endpoints or queue processors as long as you keep user data local and follow the security guidance documented in `docs/`.
