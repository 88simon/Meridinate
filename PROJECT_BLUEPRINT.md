# Meridinate - Complete Project Blueprint

**Created:** November 17, 2025
**Purpose:** Comprehensive handoff documentation for AI assistants and future development
**User:** Simon (non-technical background - use precise terminology and explanations)
**Project Status:** ✅ Monorepo migration 95% complete, production-ready

---

## Table of Contents

1. [Project Essence](#project-essence)
2. [Current Project Status](#current-project-status)
3. [Directory Structure](#directory-structure)
4. [Feature Mapping & Technical Terminology](#feature-mapping--technical-terminology)
5. [User Terminology Guide](#user-terminology-guide)
6. [Technical Stack](#technical-stack)
7. [How to Start the Project](#how-to-start-the-project)
8. [Pending Tasks](#pending-tasks)
9. [Project Roadmap](#project-roadmap)
10. [Common Operations](#common-operations)

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

### Migration Status: 95% Complete ✅

**What Just Happened:** Complete restructure from dual-repository setup to professional enterprise-grade monorepo (November 17, 2025)

#### Before (Old Structure) ❌
```
C:\Dev\
├── solscan_hotkey\     # Backend repository
└── gun-del-sol-web\    # Frontend repository
```

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
- ✅ **Database** - SQLite with 5 tables, all data preserved
- ✅ **WebSocket** - Real-time notifications working
- ✅ **Start Scripts** - Master launcher (`scripts/start.bat`) launches all services

### What Needs Cleanup ⚠️

- ⚠️ **Old directory structure** - `backend/` and `frontend/` folders at root still exist (safe to delete after testing)
- ⚠️ **Git repository** - Not yet pushed to unified GitHub repo
- ⚠️ **CI/CD workflows** - Still in per-app `.github/` folders, should be moved to root

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
│   │   │       ├── routers/                      # API endpoint handlers (8 routers)
│   │   │       │   ├── analysis.py               # Token analysis endpoints
│   │   │       │   ├── tokens.py                 # Token data retrieval
│   │   │       │   ├── wallets.py                # Wallet-related endpoints
│   │   │       │   ├── watchlist.py              # Watchlist management
│   │   │       │   ├── tags.py                   # Wallet tagging system
│   │   │       │   ├── metrics.py                # System metrics
│   │   │       │   ├── webhooks.py               # Webhook handlers
│   │   │       │   └── settings_debug.py         # Debug settings
│   │   │       ├── models/                       # Pydantic data models
│   │   │       ├── services/                     # Business logic
│   │   │       ├── database/                     # Future: DB utilities
│   │   │       ├── observability/                # Future: Logging/monitoring
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
│   │   │   │   └── analyzed_tokens.db            # Main database (22 columns, 5 tables)
│   │   │   ├── backups/                          # Database backups
│   │   │   ├── analysis_results/                 # CSV export files
│   │   │   └── axiom_exports/                    # Axiom.xyz exported data
│   │   ├── logs/                                 # Log files (gitignored)
│   │   ├── docker/                               # Docker configuration
│   │   │   ├── Dockerfile                        # Multi-stage production image
│   │   │   └── docker-compose.yml                # Container orchestration
│   │   ├── scripts/                              # Utility scripts
│   │   │   ├── backup_db.py                      # Database backup
│   │   │   └── [10+ other utility scripts]
│   │   ├── .venv/                                # Python virtual environment (Python 3.8)
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
│       │   │   │   │   ├── page.tsx              # Token list + Multi-Token Wallets panel
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
│       │   │   └── additional-tags.tsx           # Additional tag components
│       │   ├── lib/                              # Utility libraries
│       │   │   ├── api.ts                        # API client (all backend calls)
│       │   │   ├── generated/
│       │   │   │   └── api-types.ts              # Auto-generated TypeScript types from OpenAPI
│       │   │   └── debug.ts                      # Debug utilities
│       │   ├── hooks/                            # React custom hooks
│       │   │   └── useAnalysisNotifications.ts   # WebSocket notifications hook
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
├── docs/                                         # DOCUMENTATION
│   ├── migration/                                # Migration history
│   │   ├── MIGRATION_COMPLETE.md                 # Split-repo → monorepo migration
│   │   ├── MONOREPO_MIGRATION.md                 # Monorepo restructure details
│   │   ├── CLEANUP_SUMMARY.md                    # Obsolete files cleanup log
│   │   ├── DIRECTORY_REORGANIZATION_PLAN.md      # Reorganization analysis
│   │   └── START_BAT_FIX.md                      # start.bat troubleshooting
│   ├── progress/                                 # Development logs
│   │   ├── progress.md                           # Bug fix log (Nov 17, 2025)
│   │   └── CHECKLIST_ANALYSIS.md                 # Deployment checklist
│   ├── security/                                 # Security documentation
│   │   ├── SECURITY.md                           # Security policy
│   │   ├── OPSEC.md                              # Operational security
│   │   ├── SECURITY_AUDIT.md                     # Audit results
│   │   └── SECURITY_QUICKFIX.md                  # Quick security fixes
│   └── ci-cd/                                    # CI/CD guides
│       ├── CI_QUICKSTART.md
│       ├── CODECOV_SETUP.md
│       └── [10+ other CI/CD docs]
│
├── .gitignore                                    # Git ignore rules
├── README.md                                     # Main project README
├── PROJECT_BLUEPRINT.md                          # This file
└── LICENSE                                       # MIT License

OLD STRUCTURE (TO BE DELETED AFTER VERIFICATION):
├── backend/                                      # ⚠️ OLD - contains old structure remnants
└── frontend/                                     # ⚠️ OLD - contains old node_modules
```

### Key Files You Must Know

| File Path | Purpose | CRITICAL Notes |
|-----------|---------|----------------|
| `apps/backend/src/meridinate/main.py` | FastAPI app entry point | Import pattern: `python -m meridinate.main` |
| `apps/backend/src/meridinate/analyzed_tokens_db.py` | All database operations | 54KB file, handles 5 tables |
| `apps/backend/config.json` | API keys (Helius) | **NEVER commit** - contains sensitive data |
| `apps/backend/data/db/analyzed_tokens.db` | SQLite database | Main data store, 22 columns |
| `apps/frontend/src/lib/api.ts` | API client | All backend API calls go through this |
| `apps/frontend/src/lib/generated/api-types.ts` | TypeScript types | Auto-generated from OpenAPI, DO NOT edit manually |
| `apps/frontend/src/app/dashboard/tokens/page.tsx` | Main token dashboard | Where Simon spends most time |
| `scripts/start.bat` | Master launcher | Starts all 3 services (AHK, backend, frontend) |

---

## Feature Mapping & Technical Terminology

### User View → Technical Implementation

When Simon says...  →  Technical term & Implementation

#### **"Multi-Token Wallets Panel"**
- **Technical Term:** Multi-Token Wallets Data Table Component
- **What it is:** A React component that displays wallets appearing as early bidders in multiple analyzed tokens
- **Location:** `apps/frontend/src/app/dashboard/tokens/page.tsx`
- **Backend API:** `GET /api/multitokens/wallets` (router: `wallets.py`)
- **Database Query:** Joins `early_buyer_wallets` table with `analyzed_tokens` table
- **UI Component Type:** Data table (not a "panel" - panels are usually sidebar/floating elements)

**Correct Terminology:**
- ✅ "Multi-Token Wallets table"
- ✅ "Multi-Token Wallets section"
- ❌ "Multi-Token Wallets panel" (technically a page section, not a panel)

#### **"Token List" / "Main Dashboard"**
- **Technical Term:** Token Analysis Dashboard Page
- **What it is:** The main authenticated page showing all analyzed tokens
- **Location:** `apps/frontend/src/app/dashboard/tokens/page.tsx`
- **Route:** `/dashboard/tokens`
- **Components:**
  - `TokensTable` - Data table showing analyzed tokens
  - Multi-Token Wallets section (expandable)
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

#### **"Action Wheel"**
- **Technical Term:** AutoHotkey Context Menu / Radial Menu
- **What it is:** A Windows desktop automation script that provides a circular menu when right-clicking
- **Location:** `tools/autohotkey/action_wheel.ahk`
- **Functionality:**
  - Quick token analysis from clipboard
  - Open Solscan/DexScreener for selected token
  - Copy wallet addresses
- **Platform:** Windows only (AutoHotkey v2)

**Correct Terminology:**
- ✅ "AutoHotkey action wheel"
- ✅ "Right-click context menu"
- ✅ "Radial menu interface"
- ❌ "Action button" (it's a full menu system, not a single button)

#### **"Tagging Wallets"**
- **Technical Term:** Wallet Tagging System
- **What it is:** Categorization system for wallet addresses (e.g., "insider", "bot", "smart money")
- **Location (Backend):** `apps/backend/src/meridinate/routers/tags.py`
- **Location (Frontend):** `apps/frontend/src/components/wallet-tags.tsx`
- **Database Table:** `wallet_tags`
- **Context Provider:** `WalletTagsContext.tsx` (React Context for state management)

#### **"Market Cap Tracking"**
- **Technical Term:** Market Capitalization Monitoring
- **What it stores:**
  - `market_cap_usd` - At time of analysis
  - `market_cap_usd_current` - Latest refreshed value
  - `market_cap_ath` - All-time high
  - `market_cap_ath_timestamp` - When ATH occurred
- **Auto-refresh:** Background job refreshes every 30 minutes
- **API:** `POST /api/tokens/refresh` triggers manual refresh

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
| "The panel where I see wallets" | "Multi-Token Wallets table" | A data table component, not a floating panel |
| "Opening the app" | "Starting the development server" | Running `scripts/start.bat` launches 3 services |
| "The localhost page" | "Local development environment" | Browser accessing `http://localhost:3000` |
| "The backend thingy" | "FastAPI backend server" | Python server running on port 5003 |
| "When I analyze a token" | "When I submit a token analysis request" | POST request to `/api/analyze/{address}` |
| "The right-click menu" | "AutoHotkey action wheel" | Desktop automation radial menu |
| "Saving a tag on a wallet" | "Creating a wallet tag" | POST to `/api/tags` endpoint |
| "The database file" | "SQLite database" | `analyzed_tokens.db` file |
| "Refreshing the data" | "Triggering a data refresh" | Calls `/api/tokens/refresh` endpoint |
| "The token page" | "Token detail page" | Dynamic route `/dashboard/tokens/[id]` |

### Common Misconceptions to Correct

❌ **"The app crashed"**
- ✅ Correct: "The backend/frontend service stopped" or "Port 5003/3000 is not responding"
- Why: There are 3 separate services - be specific which one failed

❌ **"I need to reinstall Node.js"**
- ✅ Correct: "I need to reinstall frontend dependencies" → `cd apps/frontend && pnpm install`
- Why: Node.js is the runtime; `node_modules` are project dependencies

❌ **"The panel isn't loading"**
- ✅ Correct: "The Multi-Token Wallets table isn't rendering" or "The API request to `/api/multitokens/wallets` is failing"
- Why: Helps AI diagnose if it's a frontend rendering issue vs backend API issue

❌ **"Can you update the panel?"**
- ✅ Correct: "Can you modify the Multi-Token Wallets table component?" (if referring to UI) OR "Can you update the `/api/multitokens/wallets` endpoint?" (if referring to data)
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

**Frontend:**
```cmd
cd C:\Meridinate\apps\frontend
pnpm install
```

---

## Pending Tasks

### Immediate (Required for Clean State)

1. **⚠️ Delete Old Directory Structure**
   ```cmd
   # After verifying new structure works:
   cd C:\Meridinate
   rmdir /s backend
   rmdir /s frontend
   ```

2. **⚠️ Update .gitignore**
   ```gitignore
   # Add to root .gitignore
   apps/backend/data/
   apps/backend/logs/
   apps/backend/.venv/
   apps/backend/config.json
   apps/frontend/node_modules/
   apps/frontend/.next/
   apps/frontend/.env.local
   ```

### Soon (This Week)

3. **🔄 Git Repository Setup**
   - Create new GitHub repo: `meridinate`
   - Push unified monorepo
   - Archive old repos (`solscan_hotkey`, `gun-del-sol-web`)

4. **📝 Update README.md**
   - Add startup instructions for monorepo
   - Update architecture diagrams
   - Add troubleshooting section

### Optional (Nice to Have)

5. **🔧 Unified CI/CD**
   - Move `.github/workflows/` to root
   - Create unified workflow for both apps
   - Set up type sync validation

6. **📦 Shared Packages**
   - Create `packages/types/` for shared TypeScript types
   - Create `packages/config/` for shared configuration

7. **🚀 Deployment**
   - Set up production deployment
   - Configure environment variables for prod
   - Set up monitoring/logging

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
  - Multi-Token Wallets analysis
  - Wallet tagging system
  - Market cap tracking (ATH, current, at-analysis)
  - Watchlist service
  - AutoHotkey desktop integration

- ✅ **Phase 4: Monorepo Migration** (Nov 2025)
  - Unified repository structure
  - Professional directory organization
  - Updated build system
  - Documentation consolidation

### In Progress 🔄

- 🔄 **Phase 5: Production Hardening** (Nov-Dec 2025)
  - Clean up old directory structure
  - Unified Git repository
  - Production deployment setup
  - Performance optimization

### Planned 📋

- 📋 **Phase 6: Enhanced Analytics** (2026 Q1)
  - Wallet performance scoring
  - Predictive analysis using historical data
  - Portfolio tracking
  - Automated alerts for watchlist wallets

- 📋 **Phase 7: Data Enrichment** (2026 Q2)
  - Integration with additional data sources
  - Social sentiment analysis
  - Token holder distribution analysis
  - Contract security scanning

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

2. **Project State:** 95% complete monorepo migration - old `backend/` and `frontend/` folders still exist but are obsolete

3. **Critical Files:**
   - Database: `apps/backend/data/db/analyzed_tokens.db`
   - Config: `apps/backend/config.json` (sensitive - never commit)
   - API Client: `apps/frontend/src/lib/api.ts`
   - Main Dashboard: `apps/frontend/src/app/dashboard/tokens/page.tsx`

4. **Common User Terms:**
   - "Multi-Token Wallets panel" = Multi-Token Wallets table/section
   - "Action wheel" = AutoHotkey radial menu
   - "The app" = Usually refers to frontend at localhost:3000

5. **Start Command:** `scripts\start.bat` launches everything

### When Simon Asks About Features

1. **Map user terminology to technical components** (see Feature Mapping section)
2. **Show file paths** using markdown links: `[file.ts](path/to/file.ts:123)`
3. **Explain what's frontend vs backend** clearly
4. **Use TodoWrite tool** for multi-step tasks

### When Making Code Changes

1. **Always Read before Edit** - mandatory for existing files
2. **Test impact on both frontend and backend** if changing shared types
3. **Update OpenAPI types** if modifying backend models: `pnpm sync-types --update`
4. **Preserve data** - never modify database schema without migration plan
5. **Document breaking changes** in migration docs

### When Troubleshooting

1. **Check both frontend and backend logs**
2. **Verify ports 3000 and 5003 are available**
3. **Check virtual environment is activated** for backend
4. **Verify node_modules exists** for frontend
5. **Test API endpoints** via http://localhost:5003/docs

---

## Summary for Quick Handoff

**Project:** Solana token analysis toolkit (personal tool for investment research)

**Current State:** ✅ 95% complete monorepo migration, fully functional

**Structure:**
```
C:\Meridinate\
├── apps/backend/      # Python FastAPI (port 5003)
├── apps/frontend/     # Next.js React (port 3000)
├── tools/             # AutoHotkey + browser scripts
├── docs/              # All documentation
└── scripts/           # start.bat launches all services
```

**Start:** `scripts\start.bat` → opens 3 windows (launcher, backend, frontend)

**Main Features:**
1. Token analysis (early bidder detection)
2. Multi-Token Wallets (smart money identification)
3. Wallet tagging system
4. Market cap tracking
5. Real-time WebSocket notifications

**Pending:** Delete old `backend/` and `frontend/` folders after verification

**User:** Simon (non-technical) - explain clearly, correct terminology politely

**Critical:** Never commit `config.json`, preserve database, test before changes

---

**Document Version:** 1.0
**Last Updated:** November 17, 2025
**Next Review:** After production deployment
