# Meridinate - Complete Project Blueprint

**Created:** November 17, 2025
**Purpose:** Comprehensive handoff documentation for AI assistants and future development
**User:** Simon (non-technical background - use precise terminology and explanations)
**Project Status:** ✅ Monorepo migration 100% complete, production-ready

---

## Table of Contents

1. [Project Essence](#project-essence)
2. [Current Project Status](#current-project-status)
3. [Directory Structure](#directory-structure)
4. [Feature Mapping & Technical Terminology](#feature-mapping--technical-terminology)
5. [User Terminology Guide](#user-terminology-guide)
6. [Technical Stack](#technical-stack)
7. [How to Start the Project](#how-to-start-the-project)
8. [Project Roadmap](#project-roadmap)
9. [Common Operations](#common-operations)

---

## Project Essence

### What is Meridinate?

**Meridinate** is a **professional-grade Solana token analysis toolkit** designed to identify profitable early investment opportunities in newly launched Solana tokens by analyzing "early bidder" wallets - addresses that purchased tokens within the first few minutes of launch.

### Core Value Proposition

**Problem Solved:** Identifying which new Solana tokens have potential before they gain mainstream attention.

**How it Works:**
1. **Token Analysis** - User provides a Solana token address
2. **Early Bidder Detection** - System identifies wallets that bought within the first 5-10 minutes
3. **Wallet Profiling** - Analyzes these early bidders' historical performance across multiple tokens
4. **Multi-Token Wallet Identification** - Finds "smart money" wallets that consistently appear as early bidders in multiple successful tokens
5. **Real-time Monitoring** - Tracks market cap changes and wallet activities via WebSocket notifications

### Business Model Context

This is a **personal analysis tool** for Simon's cryptocurrency investment research, not a SaaS product. It integrates with:
- **Helius API** (Solana blockchain data)
- **DexScreener** (market cap and price data)
- **Defined.fi** (optional: additional token research)

---

## Current Project Status

### Migration Status: 100% Complete ✅

**What Just Happened:** Complete restructure from dual-repository setup to professional enterprise-grade monorepo with unified CI/CD pipeline (November 2025)

#### After (New Structure) ✅
```
C:\Meridinate\
├── apps/               # Application code
│   ├── backend/        # FastAPI + Python
│   └── frontend/       # Next.js + React
├── tools/              # Development tools (AutoHotkey, browser scripts)
├── docs/               # Documentation
└── scripts/            # Startup scripts
```

### What Works Right Now ✅

- ✅ **Backend (FastAPI)** - Runs on port 5003, all 46 API endpoints functional
- ✅ **Frontend (Next.js)** - Runs on port 3000, dashboard and token analysis working
- ✅ **AutoHotkey** - Desktop automation action wheel functional
- ✅ **Database** - SQLite with 7 tables, all data preserved
- ✅ **WebSocket** - Real-time notifications working
- ✅ **Start Scripts** - Master launcher (`scripts/start.bat`) launches all services with automatic process cleanup, uses venv Python explicitly
- ✅ **Market Cap Refresh** - "Refresh all visible market caps" button fully functional
- ✅ **Multi-Token Early Wallets UI** - Nationality dropdown and tagging system work without row highlighting issues, NEW badge indicators for recently added wallets and tokens, sortable columns for all data fields, compressed layout with 40-50% vertical space savings and fixed column widths, unified filter system with wallet tags/token status/balance/token count/top holder filters, smart search with prefix support (token:/tag:/wallet:) and fuzzy matching for typos, both filters and search persist to localStorage and URL for shareable links, bunny icon branding element next to title
- ✅ **Legacy cleanup** - Old root `backend/` and `frontend/` folders removed
- ✅ **Wallet Balances Refresh** - Single/bulk refresh shows last-updated time and green/red trend arrows
- ✅ **Token Table Performance** - Memoized rows + manual virtualization keep scrolling/selection smooth, sticky table header keeps column names visible during scroll
- ✅ **CI/CD Pipeline** - Unified monorepo workflow at `.github/workflows/monorepo-ci.yml` with all checks passing
- ✅ **UI/UX Enhancements** - GMGN.ai integration, enhanced status bar with detailed metrics, MeridinateLogo component in header, Gunslinger/Gambler tags, removed wallet count cap, horizontal pagination arrows
- ✅ **Top Holders Feature** - Configurable limit (5-20, default 10) via settings UI in Actions column header, automatically fetched during analysis, cached in database, instant modal display with Twitter/Copy icons, manual refresh updates data and credits, uses dedicated or fallback API key, dynamic modal title reflects selected limit, aligned with Helius API cap, sticky refresh button remains visible when scrolling through holder list
- ✅ **Wallet Top Holders Feature** - Clickable "TOP HOLDER" tag with notification badge in Multi-Token Early Wallets table, tabbed modal showing all tokens where wallet is a top holder, Chrome-style tabs with rank badges, wallet highlighted in holder list, cached lookups for performance
- ✅ **Top Holders Performance Optimizations (Nov 2025)** - Batch endpoint for badge counts (98% bandwidth reduction, 50 requests to 1), client-side refetch callbacks replace router.refresh() for instant updates without page reload, DEFAULT_API_SETTINGS includes topHoldersLimit for cold start compatibility
- ✅ **Token Details Modal Instant Opening (Nov 2025)** - Modal opens immediately with loading skeleton instead of blocking on network fetch, in-memory cache (30s TTL) for prefetched token data, modal state lifted from TokensTable to page.tsx to prevent table re-renders on open, background refresh ensures fresh data while showing cached content instantly
- ✅ **Token Ingestion Pipeline (Nov 2025)** - Automated tiered token discovery: Tier-0 (DexScreener, free), Tier-1 (Helius enrichment, budgeted), promotion to full analysis. Feature-flagged scheduler jobs, credit budgets, threshold filters. UI page at `/dashboard/ingestion` for queue management and manual triggers.
- ✅ **Settings Modal (Nov 2025)** - 5-tab hub: Scanning (manual scan + Solscan/Action Wheel), Ingestion (TIP thresholds/budgets/flags), SWAB (settings/stats/reconciliation), Webhooks (CRUD), System (feature flags/scheduler status). Accessible from sidebar. Includes 3-second fetch timeouts with retry buttons to prevent indefinite loading when backend is busy with ingestion operations.
- ✅ **Live Credits Bar (Nov 2025)** - Extended status bar with live credit tracking: polls every 30s with focus/visibility revalidation, clickable "API Credits Today" opens popover showing recent operations. Status bar displayed on both Scanned Tokens and Ingestion pages.
- ✅ **Persisted Operation Log (Nov 2025)** - Recent Operations history now survives restarts via `operation_log` SQLite table. Stores last 100 high-level operations (Token Analysis, Position Check, Tier-0/Tier-1, Promotion) with credits, call count, and context. Frontend fetches last 30 via `/api/stats/credits/operation-log`.
- ✅ **Sidebar Navigation Reorder (Nov 2025)** - New order: Ingestion, Scanned Tokens, Codex, Trash, Settings. Renamed "Analyzed Tokens" to "Scanned Tokens" and "Master Control" to "Settings" throughout UI.

---

## Directory Structure

### Complete Monorepo Layout

```
C:\Meridinate\                                    # PROJECT ROOT
│
├── apps/                                         # APPLICATION CODE
│   │
│   ├── backend/                                  # FASTAPI BACKEND (Python 3.11)
│   │   ├── src/                                  # Source code
│   │   │   └── meridinate/                       # Python package (IMPORTANT: package name is "meridinate")
│   │   │       ├── routers/                      # API endpoint handlers (9 routers)
│   │   │       │   ├── analysis.py               # Token analysis endpoints (includes Redis queue)
│   │   │       │   ├── tokens.py                 # Token data retrieval
│   │   │       │   ├── wallets.py                # Wallet-related endpoints
│   │   │       │   ├── watchlist.py              # Watchlist management
│   │   │       │   ├── tags.py                   # Wallet tagging system
│   │   │       │   ├── ingest.py                 # Token ingestion pipeline endpoints
│   │   │       │   ├── metrics.py                # System metrics (Prometheus)
│   │   │       │   ├── webhooks.py               # Webhook handlers
│   │   │       │   └── settings_debug.py         # Debug settings
│   │   │       ├── workers/                      # Background task workers
│   │   │       │   └── analysis_worker.py        # arq worker for async token analysis
│   │   │       ├── middleware/                   # FastAPI middleware
│   │   │       │   └── rate_limit.py             # slowapi rate limiting
│   │   │       ├── models/                       # Pydantic data models
│   │   │       ├── services/                     # Business logic
│   │   │       ├── database/                     # Future: DB utilities
│   │   │       ├── observability/                # Logging/monitoring
│   │   │       │   └── metrics.py                # Prometheus metrics collector
│   │   │       ├── analyzed_tokens_db.py         # Database operations (main DB file)
│   │   │       ├── helius_api.py                 # Helius API client
│   │   │       ├── settings.py                   # Configuration management
│   │   │       ├── debug_config.py               # Debug configuration
│   │   │       ├── secure_logging.py             # Logging utilities
│   │   │       ├── websocket.py                  # WebSocket connection manager
│   │   │       └── main.py                       # FastAPI app entry point
│   │   ├── tests/                                # Backend tests
│   │   ├── data/                                 # DATA FILES (gitignored)
│   │   │   ├── db/                               # SQLite database
│   │   │   │   └── analyzed_tokens.db            # Main database (24 columns, 5 tables)
│   │   │   ├── backups/                          # Database backups
│   │   │   ├── analysis_results/                 # Analysis result JSON files (authoritative path)
│   │   │   └── axiom_exports/                    # Axiom.xyz exported data (authoritative path)
│   │   ├── logs/                                 # Log files (gitignored)
│   │   ├── docker/                               # Docker configuration
│   │   │   ├── Dockerfile                        # Multi-stage production image
│   │   │   └── docker-compose.yml                # Container orchestration
│   │   ├── docker-compose.yml                    # Redis container for task queue (root level)
│   │   ├── .env.example                          # Environment variable template
│   │   ├── scripts/                              # Utility scripts
│   │   │   ├── backup_db.py                      # Database backup
│   │   │   └── [10+ other utility scripts]
│   │   ├── .venv/                                # Python virtual environment (Python 3.11+)
│   │   ├── config.json                           # API keys (Helius) - NEVER commit
│   │   ├── api_settings.json                     # API configuration
│   │   ├── monitored_addresses.json              # Wallet addresses
│   │   ├── requirements.txt                      # Python dependencies
│   │   ├── pyproject.toml                        # Modern Python config
│   │   └── README.md                             # Backend documentation
│   │
│   └── frontend/                                 # NEXT.JS FRONTEND (React 18, Next.js 15)
│       ├── src/
│       │   ├── app/                              # Next.js App Router (routing)
│       │   │   ├── dashboard/                    # Main dashboard (authenticated)
│       │   │   │   ├── layout.tsx                # Dashboard layout wrapper
│       │   │   │   ├── page.tsx                  # Dashboard home
│       │   │   │   ├── tokens/                   # Token analysis pages
│       │   │   │   │   ├── page.tsx              # Token list + Multi-Token Early Wallets section
│       │   │   │   │   ├── tokens-table.tsx      # Analyzed tokens data table
│       │   │   │   │   └── [id]/                 # Dynamic route for token details
│       │   │   │   │       └── page.tsx          # Individual token detail page
│       │   │   │   └── trash/                    # Deleted tokens view
│       │   │   │       └── page.tsx
│       │   │   ├── auth/                         # Clerk authentication
│       │   │   │   ├── sign-in/
│       │   │   │   └── sign-up/
│       │   │   ├── layout.tsx                    # Root layout
│       │   │   └── page.tsx                      # Landing page
│       │   ├── components/                       # Reusable UI components
│       │   │   ├── ui/                           # shadcn/ui components
│       │   │   ├── wallet-tags.tsx               # Wallet tagging UI
│       │   │   ├── additional-tags.tsx           # Additional tag components (bot, whale, insider, gunslinger, gambler)
│       │   │   ├── meridinate-logo.tsx           # MeridinateLogo SVG component (light/dark variants)
│       │   │   ├── status-bar.tsx                # Bottom status bar with metrics and API credits
│       │   │   └── layout/                       # Layout components (header, sidebar, dashboard-wrapper)
│       │   ├── lib/                              # Utility libraries
│       │   │   ├── api.ts                        # API client (all backend calls)
│       │   │   ├── generated/
│       │   │   │   └── api-types.ts              # Auto-generated TypeScript types from OpenAPI
│       │   │   └── debug.ts                      # Debug utilities
│       │   ├── hooks/                            # React custom hooks
│       │   │   ├── useAnalysisNotifications.ts   # WebSocket notifications hook
│       │   │   └── useStatusBarData.ts           # Status bar data with polling + focus revalidation
│       │   ├── contexts/                         # React Context providers
│       │   │   └── WalletTagsContext.tsx         # Wallet tags state management
│       │   ├── types/                            # TypeScript type definitions
│       │   ├── config/                           # App configuration
│       │   └── constants/                        # App constants
│       ├── public/                               # Static assets (images, fonts)
│       ├── tests/                                # E2E and unit tests
│       ├── scripts/                              # Build scripts
│       │   └── sync-api-types.ts                 # OpenAPI type generation script
│       ├── .env.local                            # Environment variables (NEVER commit)
│       ├── .env.local.example                    # Template for .env.local
│       ├── package.json                          # NPM dependencies
│       ├── next.config.ts                        # Next.js configuration
│       ├── tailwind.config.ts                    # Tailwind CSS config
│       └── README.md                             # Frontend documentation
│
├── tools/                                        # DEVELOPMENT TOOLS
│   ├── autohotkey/                               # Desktop automation (Windows only)
│   │   ├── action_wheel.ahk                      # Main action wheel interface (Right-click menu)
│   │   ├── action_wheel_settings.ini             # AHK configuration
│   │   ├── lib/                                  # AHK libraries
│   │   │   └── Gdip_All.ahk                      # Graphics library
│   │   └── tools/                                # AHK utilities
│   │       └── test_mouse_buttons.ahk
│   │
│   └── browser/                                  # Browser extensions
│       └── userscripts/                          # Tampermonkey scripts
│           └── defined-fi-autosearch.user.js     # Auto-search on Defined.fi
│
├── scripts/                                      # BUILD & DEPLOYMENT SCRIPTS
│   ├── start.bat                                 # Master launcher (all 3 services) [Windows]
│   ├── start.sh                                  # Master launcher (backend + frontend) [Unix]
│   ├── start-backend.bat                         # Backend only [Windows]
│   └── start-frontend.bat                        # Frontend only [Windows]
│
├── docs/                                         # DOCUMENTATION (historical + active)
│   ├── migration/                                # Historical migration notes
│   ├── progress/                                 # Dev logs & checklists
│   ├── security/                                 # Security policies/guides
│   ├── ci-cd/                                    # CI/CD guides
│   ├── async-tasks-rate-limiting-design.md       # Design doc for async task system
│   └── async-tasks-rate-limiting-implementation.md  # Implementation guide
│
├── .gitignore                                    # Git ignore rules
├── README.md                                     # Main project README
├── PROJECT_BLUEPRINT.md                          # This file
└── LICENSE                                       # MIT License

### Key Files You Must Know

| File Path | Purpose | CRITICAL Notes |
|-----------|---------|----------------|
| `apps/backend/src/meridinate/main.py` | FastAPI app entry point | Import pattern: `python -m meridinate.main` |
| `apps/backend/src/meridinate/analyzed_tokens_db.py` | All database operations | 65KB file, handles 6 tables |
| `apps/backend/config.json` | API keys (Helius) | **NEVER commit** - contains sensitive data |
| `apps/backend/data/db/analyzed_tokens.db` | SQLite database | Main data store, 24 columns (added top_holders_json, top_holders_updated_at) |
| `apps/backend/src/meridinate/routers/wallets.py` | Wallet endpoints | Handles balance refresh, now tracks prev/current and timestamps |
| `apps/frontend/src/lib/api.ts` | API client | All backend API calls go through this |
| `apps/frontend/src/lib/generated/api-types.ts` | TypeScript types | Auto-generated from OpenAPI, DO NOT edit manually |
| `apps/frontend/src/app/dashboard/tokens/page.tsx` | Main token dashboard | Where Simon spends most time |
| `apps/frontend/src/app/dashboard/tokens/tokens-table.tsx` | Token table component | Memoized rows, virtualized rendering for performance |
| `apps/frontend/src/app/dashboard/tokens/token-details-modal.tsx` | Token detail modal | Shows per-wallet balance trend/timestamp, links to GMGN.ai |
| `apps/frontend/src/app/dashboard/tokens/[id]/token-details-view.tsx` | Token detail page | Shows per-wallet balance trend/timestamp, links to GMGN.ai |
| `apps/frontend/src/app/dashboard/tokens/top-holders-modal.tsx` | Top holders modal | Shows top N holders for a single token with dynamic title |
| `apps/frontend/src/app/dashboard/tokens/wallet-top-holders-modal.tsx` | Wallet top holders modal | Tabbed modal showing all tokens where a wallet is a top holder |
| `apps/frontend/src/components/status-bar.tsx` | Bottom status bar | Live credit tracking with popover for recent events, polls + focus revalidation |
| `apps/frontend/src/hooks/useStatusBarData.ts` | Status bar data hook | Fetches credit stats, transactions, latest token with polling and focus revalidation |
| `apps/frontend/src/components/meridinate-logo.tsx` | MeridinateLogo component | Reusable SVG logo with light/dark variants |
| `apps/frontend/src/components/layout/header.tsx` | Main header | Contains logo, branding, navigation, user controls |
| `apps/frontend/src/components/layout/app-sidebar.tsx` | Sidebar navigation | Collapsible sidebar with nav items: Ingestion, Scanned Tokens, Codex, Trash, Settings |
| `apps/frontend/src/components/master-control-modal.tsx` | Settings modal | 5-tab settings hub: Scanning, Ingestion, SWAB, Webhooks, System |
| `scripts/start.bat` | Master launcher | Starts all 3 services (AHK, backend, frontend), uses venv Python explicitly |
| `scripts/start-backend.bat` | Backend launcher | Starts backend only, uses venv Python explicitly (line 60) |
| `scripts/start-debug.bat` | Diagnostic tool | Troubleshooting startup issues |
| `apps/backend/src/meridinate/workers/analysis_worker.py` | arq background worker | Async token analysis task processor (disabled by default) |
| `apps/backend/src/meridinate/middleware/rate_limit.py` | Rate limiting middleware | slowapi tiered rate limits (disabled by default) |
| `apps/backend/docker-compose.yml` | Redis container config | For async task queue (use `docker-compose up -d redis`) |
| `apps/backend/.env.example` | Environment template | Redis and rate limiting configuration |
| `docs/async-tasks-rate-limiting-implementation.md` | Implementation guide | Deployment instructions for async tasks & rate limiting |
| `apps/backend/data/analysis_results/` | Analysis result JSONs | Source of truth for job results (legacy copies removed) |
| `apps/backend/data/axiom_exports/` | Axiom export JSONs | Source of truth (legacy copies removed) |

---

## Feature Mapping & Technical Terminology

### User View → Technical Implementation

When Simon says...  →  Technical term & Implementation

#### **"Multi-Token Early Wallets Section"**
- **Technical Term:** Multi-Token Early Wallets Data Table Component
- **Branding:** Features bunny icon (optimized PNG via Next.js Image component) next to section title
- **What it is:** A React component that displays wallets appearing as early bidders in multiple analyzed tokens
- **Location:** `apps/frontend/src/app/dashboard/tokens/page.tsx`
- **Backend API:** `GET /api/multitokens/wallets` (router: `wallets.py`)
- **Database Query:** Joins `early_buyer_wallets` table with `analyzed_tokens` table
- **Database Tracking:** `multi_token_wallet_metadata` table tracks which wallets are newly added
- **UI Component Type:** Data table (not a "panel" - panels are usually sidebar/floating elements)

**Features:**
- **NEW Badge Indicators (Nov 2025):**
  - Green "NEW" badge appears next to wallet addresses that just crossed the 2-token threshold
  - Green "NEW" badge appears inside the token name box for the specific token that caused the wallet to become multi-token
  - Badges persist until the next token analysis completes
  - Backend tracks via `marked_at_analysis_id` field to identify which token triggered multi-token status

- **Sortable Columns (Nov 2025):**
  - Wallet Address - Sort by NEW status first, then alphabetically
  - Balance (USD) - Sort by wallet balance amount (high/low)
  - Tokens - Sort by token count (number of tokens wallet appears in)
  - Token Names - Sort by whether wallet has a NEW token
  - Click column header to toggle ascending/descending
  - Sorting persists across collapsed/expanded modes and pagination
  - Works with virtualized rendering in expanded mode

- **Compressed Layout (Nov 2025):**
  - Vertical space optimized: reduced padding (p-6 to p-3), margins, gaps, and row heights (80px to 60px)
  - Text sizes reduced throughout (headings: text-xl to text-base, body: text-sm to text-xs)
  - Button heights compressed (h-7 to h-6, h-8 to h-6)
  - Refresh balance button moved to left of balance values (horizontal layout instead of vertical stack)
  - Fixed column widths with table-fixed layout to prevent column drift on sort/scroll:
    - Wallet Address: 320px (includes address, NEW badge, Twitter/Copy buttons)
    - Balance (USD): 220px (refresh button + balance + timestamp)
    - Tags: 140px (wallet tags + additional tags popover)
    - Tokens: 80px (token count badge)
    - Token Names: auto (flexible, displays token name badges)
  - Table minimum width: 1000px with horizontal scroll if needed
  - Achieves 40-50% vertical space reduction per row while maintaining readability

**Correct Terminology:**
- ✅ "Multi-Token Early Wallets table"
- ✅ "Multi-Token Early Wallets section"
- ❌ "Multi-Token Wallets panel" (old terminology - now called "Multi-Token Early Wallets section")

#### **"Token List" / "Main Dashboard" / "Scanned Tokens"**
- **Technical Term:** Scanned Tokens Dashboard Page
- **What it is:** The main authenticated page showing all scanned tokens
- **Location:** `apps/frontend/src/app/dashboard/tokens/page.tsx`
- **Route:** `/dashboard/tokens`
- **Sidebar Label:** "Scanned Tokens" (renamed from "Analyzed Tokens" Nov 2025)
- **Components:**
  - `TokensTable` - Data table showing scanned tokens with bunny icon for "View Details" button
  - Multi-Token Early Wallets section (expandable)
  - Action buttons (Refresh, Export, etc.)

#### **"Analyzing a Token"**
- **Technical Term:** Token Analysis Request
- **What happens:**
  1. User enters Solana token address (e.g., `7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr`)
  2. Frontend calls `POST /api/analyze/{token_address}`
  3. Backend fetches token data from Helius API
  4. Identifies early bidders (first 5-10 minutes of trading)
  5. Stores results in `analyzed_tokens` table
  6. Returns analysis results + sends WebSocket notification
  7. Frontend refreshes token list automatically
- **Location:** `apps/backend/src/meridinate/routers/analysis.py`
- **Database Tables:**
  - `analyzed_tokens` - Token metadata
  - `early_buyer_wallets` - Wallet addresses + purchase data
  - `analysis_runs` - Historical analysis runs
  - `token_tags` - Token classification tags (GEM/DUD)
  - `wallet_tags` - Wallet categorization tags

#### **"Action Wheel"**
- **Technical Term:** AutoHotkey Context Menu / Radial Menu
- **What it is:** A Windows desktop automation script that provides a circular menu when right-clicking
- **Location:** `tools/autohotkey/action_wheel.ahk`
- **Functionality:**
  - Quick token analysis from clipboard
  - Open GMGN.ai/DexScreener for selected token
  - Copy wallet addresses
- **Platform:** Windows only (AutoHotkey v2)

#### **"Token Explorer Links"**
- **Technical Term:** External Token Explorer Integration
- **What it is:** Hyperlinks from token addresses/names to GMGN.ai token pages
- **Format:** `https://gmgn.ai/sol/token/{address}?min=0.1&isInputValue=true`
- **Locations:**
  - Token Names in multi-token wallets panel
  - Address column in token table
  - "View on GMGN" links in token detail modal/page
- **Previous:** Used Solscan (replaced Nov 2025)

**Correct Terminology:**
- ✅ "AutoHotkey action wheel"
- ✅ "Right-click context menu"
- ✅ "Radial menu interface"
- ❌ "Action button" (it's a full menu system, not a single button)

#### **"Tagging Wallets"**
- **Technical Term:** Wallet Tagging System
- **What it is:** Categorization system for wallet addresses (e.g., "insider", "bot", "smart money", "gunslinger", "gambler")
- **Location (Backend):** `apps/backend/src/meridinate/routers/tags.py`
- **Location (Frontend):** `apps/frontend/src/components/wallet-tags.tsx`, `apps/frontend/src/components/additional-tags.tsx`
- **Additional Tags:** Bot, Whale, Insider, Gunslinger, Gambler (managed via popover in Tags column)
- **Database Table:** `wallet_tags`
- **Context Provider:** `WalletTagsContext.tsx` (React Context for state management)

#### **"Token Classification (GEM/DUD)"**
- **Technical Term:** Token Tagging System
- **What it is:** Fire-and-forget classification system for tokens using tags ("gem" for promising tokens, "dud" for poor performers)
- **Architecture:** Uses same pattern as wallet tags - no optimistic locking, instant UI updates, simple add/remove operations
- **Location (Backend):** `apps/backend/src/meridinate/routers/tokens.py` (token tag endpoints)
- **Location (Frontend):** `apps/frontend/src/app/dashboard/tokens/tokens-table.tsx` (GEM/DUD buttons)
- **Database Table:** `token_tags` (token_id, tag, created_at)
- **API Endpoints:**
  - `GET /api/tokens/{token_id}/tags` - Get all tags for a token
  - `POST /api/tokens/{token_id}/tags` - Add a tag to a token
  - `DELETE /api/tokens/{token_id}/tags` - Remove a tag from a token
- **How it works:**
  1. Click GEM button - Removes "dud" tag if exists, adds "gem" tag
  2. Click DUD button - Removes "gem" tag if exists, adds "dud" tag
  3. Click again - Removes the tag (clears classification)
  4. Optimistic UI updates - Changes appear instantly before API confirms
  5. Cache invalidation - Both `tokens_history` and `multi_early_buyer_wallets` caches cleared
- **Display Locations:**
  - Token Table - Buttons in market cap cell, badges next to token name
  - Multi-Token Early Wallets Section - Badges shown inline with token names
- **Legacy Field:** `gem_status` column kept for backwards compatibility during migration

#### **"Top Holders Feature"**
- **Technical Term:** Token Holder Analysis System with Configurable Limit
- **What it is:** Displays the top N largest wallet holders (configurable 5-20, default 10) of a specific token with real-time balance data
- **Location (Backend):** `apps/backend/src/meridinate/helius_api.py` (lines 393-599), `apps/backend/src/meridinate/routers/tokens.py` (lines 558-660)
- **Location (Frontend):** `apps/frontend/src/app/dashboard/tokens/top-holders-modal.tsx`
- **Database Columns:** `top_holders_json`, `top_holders_updated_at` in `analyzed_tokens` table
- **API Endpoints:**
  - `GET /api/tokens/{token_address}/top-holders?limit={N}` - Fetch and refresh top N holders (limit: 5-20, aligned with Helius API cap)
  - `POST /api/settings` - Update topHoldersLimit setting (persisted to api_settings.json)
- **Configuration:**
  - Settings UI in Actions column header of tokens table (gear icon)
  - Dropdown with preset values: 5, 10, 15, 20
  - Default: 10 holders (now included in DEFAULT_API_SETTINGS for cold start compatibility)
  - Persisted to backend api_settings.json file
  - API key: uses HELIUS_TOP_HOLDERS_API_KEY if set, otherwise falls back to main HELIUS_API_KEY
- **How it works:**
  1. User configures limit via settings UI or uses default of 10
  2. Automatically fetches during token analysis using `getTokenLargestAccounts` RPC with configured limit
  3. Resolves token account addresses to wallet owner addresses using `getAccountInfo`
  4. Filters out program-derived addresses (PDAs) - only shows on-curve wallets
  5. Calculates token balance in USD using DexScreener price API
  6. Fetches total wallet balance in USD via Helius API
  7. Stores in database as JSON with timestamp
  8. Modal opens instantly with cached data, dynamically showing "Top N Token Holders" title
  9. Manual refresh button updates data using configured limit and adds credits to cumulative total
- **Data Displayed:**
  - Wallet address (clickable with Solscan filters applied)
  - Token balance in USD (calculated from token price)
  - Total wallet balance in USD
  - Twitter search link for each wallet
  - Copy to clipboard button
- **API Credits:** Adds 11-21 credits per fetch (1 for token accounts + up to 10 for owner lookups + 1 for metadata + up to 10 for wallet balances)
- **UI Features:**
  - Inline Twitter and Copy icons (same pattern as multi-token wallets panel)
  - Bottom-center refresh button
  - Last updated timestamp
  - Token name and symbol displayed prominently
  - Dynamic modal title ("Top N Token Holders" where N = configured limit)
  - Graceful fallback if no data available

#### **"Wallet Top Holders Feature" (Nov 2025)**
- **Technical Term:** Multi-Token Top Holder Analysis System with Tabbed Interface
- **What it is:** Shows all tokens where a specific wallet is a top holder, with Chrome-style tabs and notification badges
- **Location (Backend):** `apps/backend/src/meridinate/routers/wallets.py` (endpoints: `GET /wallets/{wallet_address}/top-holder-tokens`, `POST /wallets/batch-top-holder-counts`)
- **Location (Frontend):**
  - `apps/frontend/src/app/dashboard/tokens/wallet-top-holders-modal.tsx` - Tabbed modal component
  - `apps/frontend/src/app/dashboard/tokens/page.tsx` - TOP HOLDER tag in Multi-Token Early Wallets table
- **API Endpoints:**
  - `GET /wallets/{wallet_address}/top-holder-tokens` - Returns all tokens where wallet is a top holder (full data for modal)
  - `POST /wallets/batch-top-holder-counts` - Returns only counts for multiple wallets (optimized for badge display, 98% bandwidth reduction)
- **How it works:**
  1. For each wallet in Multi-Token Early Wallets table, backend searches all `top_holders_json` fields
  2. Returns list of tokens where wallet address appears, with wallet rank and holder data
  3. Frontend displays clickable "TOP HOLDER" tag with red notification badge showing count
  4. Clicking tag opens tabbed modal with Chrome-style tabs (one tab per token)
  5. Each tab shows full top holders list for that token, with current wallet highlighted
  6. Response is cached for 5 minutes to optimize performance
- **Data Returned Per Token:**
  - `token_id`, `token_name`, `token_symbol`, `token_address`
  - `top_holders` - Full list of holders from `top_holders_json`
  - `top_holders_limit` - Number of holders in the list
  - `wallet_rank` - Position of wallet in top holders (1-indexed)
  - `last_updated` - Timestamp of last refresh
- **UI Features:**
  - Purple "TOP HOLDER" tag with red circular notification badge (shows count)
  - First clickable tag in Multi-Token Early Wallets table
  - Chrome-style horizontal tabs with token names
  - Rank badge on each tab (e.g., "#3")
  - Highlighted row for the selected wallet in holders table
  - "YOU" badge next to wallet address
  - Token name, symbol, and rank prominently displayed
  - Solscan/Twitter/Copy buttons for all holders
  - Last updated timestamp at bottom
- **Performance Optimizations:**
  - Lazy-loaded modal component (dynamic import)
  - 5-minute cache for top holder lookups
  - Batch endpoint for badge counts - single POST request instead of N GET requests (98% bandwidth reduction for 50 wallets)
  - Returns only counts, not full holder lists, for badge display (3,000 holder records reduced to 50 numbers)
  - Client-side refetch callbacks replace router.refresh() for instant updates without full page reload
  - Optimistic UI updates with local state before server sync

#### **"Token Ingestion Pipeline" (Nov 2025)**
- **What it is:** Automated tiered token discovery system that ingests tokens from DexScreener, enriches with Helius data, and promotes to full analysis.
- **Architecture:** Three tiers with feature flags and credit budgets:
  - **Tier-0 (free):** Hourly DexScreener fetch of recently migrated tokens, stores MC/volume/liquidity snapshots in `token_ingest_queue` table.
  - **Tier-1 (budgeted):** Every 4 hours, enriches tokens passing thresholds (MC, volume, liquidity, age) with Helius metadata/holders, respects credit budget.
  - **Promotion:** Manual or auto-promote enriched tokens to full analysis (early bidder detection, MTEW positions, SWAB webhooks).
- **Location (Backend):**
  - `routers/ingest.py` - 8 REST endpoints for settings, queue, triggers
  - `tasks/ingest_tasks.py` - Tier-0/Tier-1/promotion logic
  - `services/dexscreener_service.py` - DexScreener API client
  - `scheduler.py` - Feature-flagged scheduler jobs
- **Location (Frontend):** `app/dashboard/ingestion/page.tsx` - Queue management UI with stats, filters, manual triggers
- **Database:** `token_ingest_queue` table (address, name, symbol, tier, status, MC/volume snapshots, timestamps)
- **Settings:** `ingest_settings.json` - thresholds, batch sizes, credit budgets, feature flags (`ingest_enabled`, `enrich_enabled`, `auto_promote_enabled`, `hot_refresh_enabled`)
- **API Endpoints:**
  - `GET/POST /api/ingest/settings` - View/update settings
  - `GET /api/ingest/queue` - List queue with filters
  - `GET /api/ingest/queue/stats` - Queue statistics
  - `POST /api/ingest/run-tier0` - Trigger Tier-0 ingestion
  - `POST /api/ingest/run-tier1` - Trigger Tier-1 enrichment
  - `POST /api/ingest/promote` - Promote tokens to full analysis
  - `POST /api/ingest/discard` - Mark tokens discarded
  - `POST /api/ingest/refresh-hot` - Refresh MC/volume for recent tokens
  - `POST /api/ingest/auto-promote` - Trigger auto-promotion
- **Key Behavior:** Promotion runs full `TokenAnalyzer.analyze_token()`, saves to `analyzed_tokens` with `ingest_source`/`ingest_tier` metadata, records MTEW positions, registers SWAB webhooks.

#### **"SWAB - Smart Wallet Archive Builder" (Nov 2025)**
- **What it is:** Tracks MTEW wallets across tokens, detecting buys/sells and computing PnL.
- **Where:** Backend (`routers/swab.py`, `routers/webhooks.py`, `tasks/position_tracker.py`, `analyzed_tokens_db.py`, `helius_api.py`); Frontend (`components/swab/*`, `lib/api.ts`).
- **How PnL works:**  
  - Holding: `current_mc / entry_mc` (unrealized, updates with price).  
  - Sold: exit price ÷ avg entry (frozen); FPnL shows `current_mc / entry_mc` (what-if).  
- **Data flow:**  
  - Webhook-first: Helius webhooks → `/webhooks/callback` → `_process_swab_sell` records sells with live DexScreener price (no credits).  
  - Fallback: `get_recent_token_transaction` scans recent signatures (credit-cost, limited window).  
  - Reconciliation: `/api/swab/reconcile[...]` tries to fix positions with `total_sold_usd=0`; limited to ~100 signatures for active wallets.  
- **Limits:** If webhook wasn’t active before a sell, or the sell is older than the signature window, PnL falls back to MC ratios. Reconciliation can miss active wallets; price-based PnL requires webhook/live capture.
  - Filter popover for status, wallet, token filtering

#### **"Multi-Token Early Wallets Filter and Search System" (Nov 2025)**
- **Technical Term:** Unified Filter and Smart Search Interface for Multi-Token Early Wallets Table
- **What it is:** Comprehensive filtering and search system with smart prefix support, fuzzy matching, and persistent state
- **Location (Frontend):** `apps/frontend/src/app/dashboard/tokens/page.tsx`
- **Components:**
  - Filter popover with multiple categories
  - Smart search bar with info popover documentation
  - Active filter chips display
  - Badge counter on filter button
- **Filter Categories:**
  - Wallet Tags - Filter by Bot, Whale, Insider, Gunslinger, Gambler (OR logic within category)
  - Token Status - Has GEMs, Has DUDs, Has untagged, All GEMs, All DUDs (OR logic within category)
  - Balance Range - Min/Max USD range with quick presets (>$1k, >$10k, >$100k)
  - Token Count Range - Min/Max number of tokens with quick presets (2+, 5+, 10+)
  - Top Holder Status - Is top holder checkbox
- **Filter Logic:**
  - OR logic within each category (e.g., "Has GEMs" OR "Has DUDs")
  - AND logic across categories (e.g., "Has GEMs" AND "Balance > $1k")
  - Combines with search using AND logic
- **Smart Search Features:**
  - Prefix-based searching for precision:
    - `token:Ant` - Search only token names
    - `tag:bot` - Search only wallet tags
    - `wallet:5e8S` - Search only wallet addresses
    - `gem` or `dud` - Search by token status
  - General search (no prefix) - Searches all fields simultaneously
  - Multiple terms supported with AND logic (e.g., `gem token:Ant`)
  - Fuzzy matching with 70% similarity threshold for typo tolerance
  - Real-time filtering with proper dependency management
- **Search Algorithm:**
  - Custom fuzzy match function calculates character-order similarity
  - Exact substring matches score 100%
  - Boosts score if target starts with query
  - Examples: "clot" matches "CLOUT" (80%), "veloity" matches "VELOCITY" (87%)
- **Persistence:**
  - Filters persist to localStorage (key: `mtwFilters`)
  - Search query persists to localStorage (key: `mtwSearch`)
  - Both sync to URL query parameters for shareable filtered views
  - URL format: `?mtwFilters=...&search=...`
  - Auto-loads from both sources on page mount
- **UI Features:**
  - Centered layout - Filters button and search bar positioned at top-center
  - Info icon next to search bar opens popover with usage guide
  - Active filter chips below search bar with individual remove buttons
  - Clear all filters option when multiple active
  - Badge counter shows number of active filters
  - Search clear button (X) appears when text is present
- **Performance:**
  - Debounced filtering prevents lag during typing
  - Proper React memoization with stable object references
  - Wallet tags fetched via batch API endpoint (`POST /wallets/batch-tags`)
  - Filters and search combined in single pass through data

#### **"Market Cap Tracking"**
- **Technical Term:** Market Capitalization Monitoring
- **What it stores:**
  - `market_cap_usd` - At time of analysis
  - `market_cap_usd_current` - Latest refreshed value
  - `market_cap_ath` - All-time high
  - `market_cap_ath_timestamp` - When ATH occurred
- **Refresh mechanism:** Manual only - no background job
- **API:** `POST /api/tokens/refresh-market-caps` (user-triggered via "Refresh all visible market caps" button)
- **How it works:** User clicks refresh button, frontend sends token IDs to endpoint, backend fetches latest prices from Helius DAS API

#### **"Watchlist"**
- **Technical Term:** Wallet Watchlist Service
- **What it is:** System for monitoring specific wallet addresses for new token purchases
- **Location:** `apps/backend/src/meridinate/services/watchlist_service.py`
- **Frontend:** `/dashboard` page
- **Use Case:** Track "smart money" wallets to get notified when they buy new tokens

#### **"Trash" / "Deleted Tokens"**
- **Technical Term:** Soft Delete System
- **What it is:** Tokens marked as deleted (not permanently removed)
- **Database Column:** `deleted_at` (timestamp, NULL = not deleted)
- **Frontend Route:** `/dashboard/trash`
- **Functionality:** Can be restored or permanently deleted

---

## User Terminology Guide

### For Simon (Non-Technical Background)

When discussing the project with AI assistants, use these precise terms:

| What Simon Might Say | Correct Technical Term | Explanation |
|----------------------|------------------------|-------------|
| "The panel where I see wallets" / "Multi-Token Wallets" | "Multi-Token Early Wallets table/section" | Renamed to emphasize early bidder analysis - features bunny icon branding |
| "Opening the app" | "Starting the development server" | Running `scripts/start.bat` launches 3 services |
| "The localhost page" | "Local development environment" | Browser accessing `http://localhost:3000` |
| "The backend thingy" | "FastAPI backend server" | Python server running on port 5003 |
| "When I analyze a token" | "When I submit a token analysis request" | POST request to `/api/analyze/{address}` |
| "The right-click menu" | "AutoHotkey action wheel" | Desktop automation radial menu |
| "Saving a tag on a wallet" | "Creating a wallet tag" | POST to `/api/tags` endpoint |
| "The database file" | "SQLite database" | `analyzed_tokens.db` file |
| "Refreshing the data" | "Triggering a data refresh" | Calls `/api/tokens/refresh` endpoint |
| "The token page" | "Token detail page" | Dynamic route `/dashboard/tokens/[id]` |
| "Settings" / "Master Control" | "Settings modal" | 5-tab settings hub opened from sidebar |
| "Scanned Tokens" / "Analyzed Tokens" | "Scanned Tokens page" | Main dashboard at `/dashboard/tokens` |

### Common Misconceptions to Correct

❌ **"The app crashed"**
- ✅ Correct: "The backend/frontend service stopped" or "Port 5003/3000 is not responding"
- Why: There are 3 separate services - be specific which one failed

❌ **"I need to reinstall Node.js"**
- ✅ Correct: "I need to reinstall frontend dependencies" → `cd apps/frontend && pnpm install`
- Why: Node.js is the runtime; `node_modules` are project dependencies

❌ **"The panel isn't loading"**
- ✅ Correct: "The Multi-Token Early Wallets table isn't rendering" or "The API request to `/api/multitokens/wallets` is failing"
- Why: Helps AI diagnose if it's a frontend rendering issue vs backend API issue

❌ **"Can you update the panel?"**
- ✅ Correct: "Can you modify the Multi-Token Early Wallets table component?" (if referring to UI) OR "Can you update the `/api/multitokens/wallets` endpoint?" (if referring to data)
- Why: Clarifies whether it's a frontend or backend change

---

## Technical Stack

### Backend (FastAPI + Python)

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Framework** | FastAPI | 0.109+ | REST API framework |
| **Runtime** | Python | 3.11 | Programming language |
| **Server** | Uvicorn | 0.27+ | ASGI server |
| **Database** | SQLite | 3.x | Embedded database |
| **DB Access** | aiosqlite | - | Async SQLite driver |
| **API Client** | httpx | 0.26+ | Async HTTP client |
| **WebSocket** | websockets | 12.0+ | Real-time notifications |
| **JSON** | orjson | 3.9+ | Fast JSON serialization |
| **Validation** | Pydantic | 2.0+ | Data validation |

### Frontend (Next.js + React)

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Framework** | Next.js | 15.3.2 | React framework |
| **Library** | React | 18.x | UI library |
| **Language** | TypeScript | 5.x | Type-safe JavaScript |
| **Bundler** | Turbopack | - | Fast build tool |
| **Styling** | Tailwind CSS | 3.x | Utility-first CSS |
| **UI Components** | shadcn/ui | - | Accessible component library |
| **Package Manager** | pnpm | 10.21+ | Fast package manager |
| **Auth** | Clerk | - | Authentication |
| **State** | React Context | - | Global state management |
| **Forms** | React Hook Form | - | Form validation |

### Tools & Services

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Desktop Automation** | AutoHotkey v2 | Windows automation |
| **API Provider** | Helius API | Solana blockchain data |
| **Price Data** | DexScreener | Market cap & price |
| **Browser Automation** | Tampermonkey | Userscript management |
| **Monitoring** | Axiom.xyz | Log aggregation (optional) |

---

## How to Start the Project

### Prerequisites

- Python 3.11+ installed
- Node.js 20+ installed
- pnpm installed (`npm install -g pnpm`)
- AutoHotkey v2 (optional, Windows only)

### Starting All Services (Recommended)

```cmd
cd C:\Meridinate
scripts\start.bat
```

This launches:
1. ✅ AutoHotkey action wheel
2. ✅ Backend (FastAPI on port 5003)
3. ✅ Frontend (Next.js on port 3000)

**What you'll see:**
- Launcher window stays open with clickable URLs
- Backend window shows FastAPI startup logs
- Frontend window shows Next.js compilation

**Access:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:5003
- API Docs: http://localhost:5003/docs
- Health Check: http://localhost:5003/health

### Starting Individual Services

**Backend Only:**
```cmd
cd C:\Meridinate
scripts\start-backend.bat
```

**Frontend Only:**
```cmd
cd C:\Meridinate
scripts\start-frontend.bat
```

### First Time Setup

If dependencies aren't installed:

**Backend:**
```cmd
cd C:\Meridinate\apps\backend
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

**Dependencies installed:**
- Core: `fastapi`, `uvicorn`, `requests`, `aiosqlite`, `httpx`, `orjson`, `aiofiles`
- Blockchain: `solana`, `base58`
- Task Queue: `arq`, `redis` (disabled by default)
- Rate Limiting: `slowapi` (disabled by default)

**Frontend:**
```cmd
cd C:\Meridinate\apps\frontend
pnpm install
```

**Important Notes:**
- ✅ Startup scripts ([start.bat](scripts/start.bat), [start-backend.bat](scripts/start-backend.bat)) automatically use `.venv\Scripts\python.exe` to avoid module import errors
- ✅ No need to manually activate virtual environment before running start scripts
- ⚠️ If running Python directly, use `.venv\Scripts\python.exe -m meridinate.main` from backend directory

---

## Project Roadmap

### Completed ✅

- ✅ **Phase 1: Core Analysis Engine** (2024 Q4)
  - Token analysis via Helius API
  - Early bidder detection algorithm
  - Database schema design
  - CSV export functionality

- ✅ **Phase 2: Frontend Dashboard** (2025 Q1)
  - Next.js 15 App Router implementation
  - shadcn/ui component library integration
  - Real-time WebSocket notifications
  - Clerk authentication

- ✅ **Phase 3: Advanced Features** (2025 Q2-Q3)
  - Multi-Token Early Wallets analysis
  - Wallet tagging system
  - Market cap tracking (ATH, current, at-analysis)
  - Watchlist service
  - AutoHotkey desktop integration

- ✅ **Phase 4: Monorepo Migration** (Nov 2025)
  - Unified repository structure
  - Professional directory organization
  - Updated build system
  - Documentation consolidation

- ✅ **Phase 4.5: Critical Bug Fixes** (Nov 17-18, 2025)
  - fixed market cap refresh functionality (route ordering, react hooks, database locking)
  - fixed multi-token wallets nationality dropdown row highlighting
  - enhanced start scripts with automatic process cleanup
  - pushed unified repository to github

- ✅ **Phase 5: Async Tasks & CI/CD** (Nov 19-20, 2025)
  - Async task queue with arq + Redis (disabled by default)
  - Rate limiting with slowapi (disabled by default)
  - Unified monorepo CI/CD pipeline at `.github/workflows/monorepo-ci.yml`
  - API type synchronization validation in CI
  - Cross-platform CI fixes (PYTHONPATH, database directory, Python command)
  - Fixed API types sync infinite loop (excluded commit SHA from comparison)

- ✅ **Phase 6: UI/UX Enhancements** (Nov 20, 2025)
  - GMGN.ai integration - replaced Solscan links across all token views
  - Extended tagging system - added Gunslinger and Gambler tags
  - MeridinateLogo component - reusable SVG logo with light/dark variants
  - Header redesign - logo moved outside sidebar, sidebar toggle moved inside
  - Enhanced status bar - detailed analysis metrics (token name, wallets found, API credits)
  - API credits tracking - "Total API Credits Used Today" metric
  - Settings improvements - removed wallet count cap (was 50, now unlimited)
  - UX polish - reduced page title font sizes, horizontal pagination arrows

### In Progress 🔄

- 🔄 **Phase 7: Production Hardening** (Nov-Dec 2025)
  - Production deployment setup
  - Performance optimization
  - Monitoring and alerting setup

### Planned 📋

- 📋 **Phase 8: Enhanced Analytics** (2026 Q1)
  - Wallet performance scoring
  - Predictive analysis using historical data
  - Portfolio tracking
  - Automated alerts for watchlist wallets

- 📋 **Phase 9: Data Enrichment** (2026 Q2)
  - Integration with additional data sources
  - Social sentiment analysis
  - Token holder distribution analysis
  - Contract security scanning

---

## Historical Bug Fixes & Optimizations

For detailed historical bug fixes, performance optimizations, and technical implementation notes, see [docs/CHANGELOG.md](docs/CHANGELOG.md).

**Recent Major Changes:**
- Frontend performance optimizations (CSS transitions, memoization, virtualization)
- WebSocket resource management with tab visibility API
- Backend caching and HTTP session reuse
- PWA implementation with Workbox service worker
- Async task queue and rate limiting infrastructure (disabled by default)

---

## Common Operations

### Database Operations

**View Database Tables:**
```cmd
cd C:\Meridinate\apps\backend
sqlite3 data/db/analyzed_tokens.db ".tables"
```

**Backup Database:**
```cmd
cd C:\Meridinate\apps\backend
python scripts/backup_db.py
```

**View Table Schema:**
```sql
sqlite3 data/db/analyzed_tokens.db ".schema analyzed_tokens"
```

### Type Synchronization

**Generate TypeScript types from backend OpenAPI:**
```cmd
cd C:\Meridinate\apps\frontend
pnpm sync-types --update
```

### Testing

**Run Backend Tests:**
```cmd
cd C:\Meridinate\apps\backend
pytest tests/ -v --cov=meridinate
```

**Run Frontend Tests:**
```cmd
cd C:\Meridinate\apps\frontend
pnpm test           # Unit tests
pnpm test:e2e       # E2E tests
```

### Code Quality

**Backend:**
```cmd
cd C:\Meridinate\apps\backend
black src/meridinate/           # Format code
flake8 src/meridinate/          # Lint
mypy src/meridinate/            # Type check
```

**Frontend:**
```cmd
cd C:\Meridinate\apps\frontend
pnpm lint           # ESLint
pnpm format         # Prettier
pnpm typecheck      # TypeScript
```

### Common Troubleshooting

**Issue: Backend won't start**
```cmd
# Check if port 5003 is in use
netstat -ano | findstr :5003

# Kill process on port 5003
taskkill /PID <PID> /F

# Activate venv and run
cd C:\Meridinate\apps\backend
.venv\Scripts\activate.bat
cd src
python -m meridinate.main
```

**Issue: Frontend won't start**
```cmd
# Check if port 3000 is in use
netstat -ano | findstr :3000

# Reinstall dependencies
cd C:\Meridinate\apps\frontend
rm -rf node_modules pnpm-lock.yaml .next
pnpm install
pnpm dev
```

**Issue: "next" command not found**
```cmd
# This means node_modules is incomplete
cd C:\Meridinate\apps\frontend
pnpm install
```

---

## Handoff Instructions for AI Assistants

### Context You Must Know

1. **User Background:** Simon is non-technical - always explain concepts clearly and correct imprecise terminology politely

2. **Project State:** 100% complete monorepo migration with unified CI/CD - legacy root `backend/` and `frontend/` folders removed

3. **Critical Files:**
   - Database: `apps/backend/data/db/analyzed_tokens.db`
   - Config: `apps/backend/config.json` (sensitive - never commit)
   - API Client: `apps/frontend/src/lib/api.ts`
   - Main Dashboard: `apps/frontend/src/app/dashboard/tokens/page.tsx`

4. **Common User Terms:**
   - "Multi-Token Wallets panel" = Multi-Token Early Wallets table/section (renamed with bunny icon branding)
   - "Action wheel" = AutoHotkey radial menu
   - "The app" = Usually refers to frontend at localhost:3000
   - "Settings" or "Master Control" = Settings modal (5-tab hub)
   - "Scanned Tokens" or "Analyzed Tokens" = Main token dashboard

5. **Start Command:** `scripts\start.bat` launches everything

### When Simon Asks About Features

1. **Map user terminology to technical components** (see Feature Mapping section)
2. **Show file paths** using markdown links: `[file.ts](path/to/file.ts:123)`
3. **Explain what's frontend vs backend** clearly

### When Making Code Changes

1. **Always Read before Edit** - mandatory for existing files
2. **Test impact on both frontend and backend** if changing shared types
3. **Update OpenAPI types** if modifying backend models: `pnpm sync-types --update`
4. **Preserve data** - never modify database schema without migration plan
5. **Document breaking changes** in migration docs
6. **Backend cache:** Any mutation that changes the token list/fields should invalidate the `tokens_history` cache key (already handled for analysis save, deletes, market-cap refresh)

### When Troubleshooting

1. **Check both frontend and backend logs**
2. **Verify ports 3000 and 5003 are available**
3. **Check virtual environment is activated** for backend
4. **Verify node_modules exists** for frontend
5. **Test API endpoints** via http://localhost:5003/docs

---

## Summary for Quick Handoff

**Project:** Solana token analysis toolkit (personal tool for investment research)

**Current State:** ✅ 100% complete monorepo migration with unified CI/CD, fully functional

**Structure:**
```
C:\Meridinate\
├── apps/backend/      # Python FastAPI (port 5003)
├── apps/frontend/     # Next.js React (port 3000)
├── tools/             # AutoHotkey + browser scripts
├── docs/              # All documentation
└── scripts/           # start.bat launches all services
```

**Sidebar Nav:** Ingestion, Scanned Tokens, Codex, Trash, Settings

**Start:** `scripts\start.bat` → opens 3 windows (launcher, backend, frontend)

**Main Features:**
1. Token analysis (early bidder detection)
2. Multi-Token Early Wallets (smart money identification with bunny icon branding)
3. Wallet tagging system
4. Market cap tracking (with trend/last-updated)
5. Wallet balance refresh (with trend/last-updated)
6. Real-time WebSocket notifications
7. Persisted operation log (Recent Operations survives restarts)
8. Settings modal (5-tab hub for scanning, ingestion, SWAB, webhooks, system)

**CI/CD:** `.github/workflows/monorepo-ci.yml` - Backend tests, frontend lint/format/typecheck, API types sync, production builds

**User:** Simon (non-technical) - explain clearly, correct terminology politely

**Critical:** Never commit `config.json`, preserve database, test before changes
**Data paths:** All writable data lives in `apps/backend/data/...` (db, analysis_results, axiom_exports). Legacy duplicates under `apps/backend/src/meridinate/` were removed.

---

**Document Version:** 2.4
**Last Updated:** November 30, 2025 (Settings modal timeout/retry during ingestion)
**Next Review:** After production deployment
