# Meridinate Frontend

[![Node.js](https://img.shields.io/badge/node-22.x-brightgreen)](https://nodejs.org/)
[![pnpm](https://img.shields.io/badge/pnpm-10.x-orange)](https://pnpm.io/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-blue)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)

Modern Next.js web dashboard for Meridinate - Solana token analysis and wallet monitoring platform.

## Overview

Production-ready React application built with modern web technologies:

- **Framework:** [Next.js 15](https://nextjs.org/15) with App Router and Turbopack
- **Language:** [TypeScript 5.7](https://www.typescriptlang.org) with strict type checking
- **Styling:** [Tailwind CSS v4](https://tailwindcss.com)
- **Components:** [shadcn/ui](https://ui.shadcn.com) - accessible, customizable components
- **Data Tables:** [TanStack Table v8](https://tanstack.com/table/latest) with advanced filtering
- **State Management:** React hooks + Context API
- **Real-time:** WebSocket integration for live updates
- **Linting:** [ESLint](https://eslint.org) with TypeScript rules
- **Formatting:** [Prettier](https://prettier.io)

## Features

### Token Analysis Dashboard

- **Comprehensive Token View** - List all analyzed tokens with detailed metrics
- **Historical Analysis** - View past analysis runs with wallet breakdowns
- **Trash Management** - Soft-delete tokens with restore/permanent delete options
- **Advanced Filtering** - Filter by name, symbol, date, market cap, wallet count
- **Sorting & Pagination** - Sort by any column, adjustable page sizes

### Market Cap Tracking

- **Dual Market Cap Display** - Original (at analysis time) + current (refreshed) values
- **Individual Refresh** - Per-row refresh icons for single token updates
- **Bulk Refresh** - Update all visible or selected tokens at once
- **Instant UI Updates** - Optimistic updates without page reload
- **Change Indicators** - Color-coded arrows (green ▲ increase, red ▼ decrease)
- **Timestamps** - Shows when market cap was last refreshed
- **Dual-source Strategy** - DexScreener (free) with Helius fallback

### Wallet Balance Tracking

- **Real-time SOL Balances** - Accurate USD values with live SOL pricing
- **Column Header Refresh** - Bulk balance updates for all visible wallets
- **Per-row Refresh** - Individual wallet balance updates
- **API Credit Tooltips** - Shows cost of each operation
- **Instant UI Updates** - No page reload required
- **CoinGecko Integration** - Real-time SOL/USD pricing (5-min cache)

### Tags & Codex

- **Wallet Tagging** - Custom tags + nationality tags (US, CN, KR, JP, EU, UK, SG, IN, RU, BR, CA, AU)
- **Codex Panel** - Wallet directory with token counts (excludes deleted tokens)
- **Tag Filtering** - Filter tokens by wallet tags
- **KOL Marking** - Flag Key Opinion Leaders for special tracking

### Real-time WebSocket Notifications

- **Analysis Completion** - Live notifications when token analysis finishes
- **Toast Notifications** - User-friendly alerts with token details
- **Smart Connection Management:**
  - Single WebSocket connection per tab (singleton pattern)
  - Auto-cleanup after 30s of tab inactivity
  - Smart reconnection only when tab is visible
  - Linear backoff (3s, 6s, 9s, 12s, 15s intervals, max 30s)
  - Max 5 retry attempts with user notification
  - Page Visibility API integration
  - Prevents browser resource exhaustion

### Solscan Settings Management

- **Centralized Control Panel** - Configure Solscan URL parameters
- **Activity Type Dropdown** - SPL Transfer, SOL Transfer, etc.
- **Minimum Value Filter** - Arrow controls and drag-to-adjust
- **Page Size Selection** - 10, 20, 30, 40, 60, 100
- **Auto-save** - Persists after 300ms of changes
- **Dynamic URL Generation** - Multi-token wallet hyperlinks
- **AHK Integration** - Syncs with AutoHotkey action wheel via INI file

### Performance Optimizations

- **CSS Transitions** - Replaced Framer Motion with native CSS for better performance
- **Memoization** - Heavy table cells memoized to prevent unnecessary re-renders
- **Deferred State Updates** - Selection updates batched for smooth UX
- **Optimistic Updates** - Instant UI feedback for user actions
- **Code Splitting** - Route-based code splitting with Next.js

## Getting Started

### Prerequisites

- **Node.js 22+** installed
- **pnpm 10+** installed (`npm install -g pnpm`)
- **Backend running** on `http://localhost:5003`

### Installation

From monorepo root:

```bash
cd apps/frontend

# Install dependencies
pnpm install

# Start development server
pnpm dev
```

Or use monorepo scripts:

**Windows:**
```cmd
scripts\start-frontend.bat
```

**macOS/Linux:**
```bash
chmod +x scripts/start-frontend.sh
./scripts/start-frontend.sh
```

### Access the Application

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:5003
- **API Docs:** http://localhost:5003/docs

## Project Structure

```
apps/frontend/
├── src/
│   ├── app/                    # Next.js App Router
│   │   ├── dashboard/          # Dashboard pages
│   │   │   └── tokens/         # Token analysis pages
│   │   ├── api/                # API routes
│   │   ├── layout.tsx          # Root layout
│   │   └── page.tsx            # Home page
│   ├── components/             # React components
│   │   ├── ui/                 # shadcn/ui components
│   │   ├── layout/             # Layout components
│   │   ├── forms/              # Form components
│   │   └── ...                 # Feature components
│   ├── lib/                    # Utilities
│   │   ├── api.ts              # Backend API client
│   │   ├── generated/          # Auto-generated types
│   │   │   └── api-types.ts    # OpenAPI TypeScript types
│   │   └── utils.ts            # Shared utilities
│   ├── hooks/                  # Custom React hooks
│   │   ├── useAnalysisNotifications.ts  # WebSocket hook
│   │   └── ...                 # Other hooks
│   ├── types/                  # TypeScript types
│   ├── contexts/               # React contexts
│   └── config/                 # App configuration
├── public/                     # Static assets
├── scripts/                    # Build/sync scripts
│   └── sync-api-types.ts       # OpenAPI type sync
├── tests/                      # E2E and unit tests
│   └── e2e/                    # Playwright E2E tests
├── package.json
├── next.config.ts              # Next.js configuration
├── tsconfig.json               # TypeScript configuration
├── tailwind.config.ts          # Tailwind CSS configuration
└── README.md                   # This file
```

## Backend Integration

### API Client

The frontend uses a type-safe API client (`lib/api.ts`) that connects to the FastAPI backend on port 5003.

### API Types Synchronization

Frontend TypeScript types are **auto-generated** from the backend OpenAPI schema:

```bash
cd apps/frontend

# Check if types are in sync
pnpm sync-types:check

# Update types from backend
pnpm sync-types:update
```

**How it works:**

1. Generates OpenAPI schema from backend FastAPI app
2. Uses `openapi-typescript` to create TypeScript types
3. Formats with Prettier to match project style
4. Compares with committed types to ensure sync

**In CI/CD:**

The monorepo CI workflow automatically checks that frontend types match the backend schema. PRs will fail if types are out of sync.

### WebSocket Integration

Real-time notifications via WebSocket connection:

```typescript
import { useAnalysisNotifications } from '@/hooks/useAnalysisNotifications';

function Component() {
  useAnalysisNotifications(); // Automatically connects and handles notifications

  // Notifications appear as toast messages when analysis completes
}
```

**Features:**

- Singleton connection per tab
- Automatic reconnection with exponential backoff
- Tab visibility detection (closes after 30s when hidden)
- Max 5 retry attempts
- Error handling with user notifications

## Development

### Available Commands

```bash
# Development
pnpm dev              # Start dev server with Turbopack
pnpm build            # Production build
pnpm start            # Start production server

# Code Quality
pnpm lint             # Run ESLint
pnpm lint:strict      # Strict ESLint (warnings as errors)
pnpm lint:fix         # Auto-fix linting issues
pnpm format           # Format with Prettier
pnpm format:check     # Check formatting
pnpm type-check       # TypeScript type checking

# API Types
pnpm sync-types:check # Check if types match backend
pnpm sync-types:update # Update types from backend

# Testing
pnpm test             # Run unit tests (future)
pnpm test:e2e         # Run Playwright E2E tests

# CI Checks
run_ci_checks.bat     # Windows: Run all CI checks
./run_ci_checks.sh    # Unix: Run all CI checks
```

### Local Development Workflow

1. **Start backend** (from monorepo root):
   ```bash
   scripts\start-backend.bat
   ```

2. **Start frontend** (from monorepo root):
   ```bash
   scripts\start-frontend.bat
   ```

3. **Make changes** to components/pages

4. **Check types** if you modified API calls:
   ```bash
   cd apps/frontend
   pnpm sync-types:check
   ```

5. **Run CI checks** before committing:
   ```bash
   cd apps/frontend
   run_ci_checks.bat
   ```

### Adding New Features

1. **Create component** in `src/components/`
2. **Add route** (if needed) in `src/app/`
3. **Use API types** from `src/lib/generated/api-types.ts`
4. **Update API client** in `src/lib/api.ts` if adding new endpoints
5. **Add tests** in `tests/e2e/` for critical flows
6. **Sync API types** if backend changed:
   ```bash
   pnpm sync-types:update
   ```

## CI/CD

### Monorepo CI Workflow

Located at `../../.github/workflows/monorepo-ci.yml`:

**Jobs:**

1. **Backend Tests** - pytest with new dependencies (arq, redis, slowapi)
2. **Frontend Lint** - ESLint and Prettier checks
3. **Frontend TypeScript** - Type checking
4. **API Types Sync** - Validates frontend types match backend
5. **Frontend Build** - Next.js production build
6. **All Checks** - Summary job with PR comments

### Local CI Checks

Run the same checks locally before pushing:

**Windows:**
```cmd
run_ci_checks.bat
```

**macOS/Linux:**
```bash
chmod +x run_ci_checks.sh
./run_ci_checks.sh
```

These scripts run:
- ESLint (normal + strict mode)
- Prettier formatting check
- TypeScript type checking
- Next.js build verification

### Legacy Workflows

The `.github/workflows/` directory in this app contains legacy workflows from before the monorepo migration. The root-level monorepo workflow (`../../.github/workflows/monorepo-ci.yml`) is now the primary CI/CD pipeline.

**Note:** E2E tests are still handled by the app-level workflow if needed.

## Environment Variables

Create `.env.local` for local development:

```bash
# Backend API URL
NEXT_PUBLIC_API_URL=http://localhost:5003

# Feature flags
NEXT_PUBLIC_SENTRY_DISABLED=true
NEXT_TELEMETRY_DISABLED=1

# Development
NODE_ENV=development
```

**Production:**

```bash
NEXT_PUBLIC_API_URL=https://api.meridinate.com
NEXT_PUBLIC_SENTRY_DISABLED=false
NODE_ENV=production
```

## Performance

### Optimizations Applied

1. **Replaced Framer Motion with CSS Transitions**
   - Native browser animations
   - Lower JavaScript overhead
   - Smoother 60fps animations

2. **Memoized Heavy Table Cells**
   - React.memo for expensive components
   - Prevents unnecessary re-renders
   - Stable during sorting/filtering

3. **Deferred State Updates**
   - Batched selection updates
   - Smooth UX during bulk operations
   - No UI blocking

4. **Optimistic Updates**
   - Instant UI feedback for user actions
   - Background API sync
   - Error rollback if needed

5. **WebSocket Resource Management**
   - Single connection per tab
   - Auto-cleanup when inactive
   - Smart reconnection logic
   - Prevents "insufficient resources" errors

### Lighthouse Scores

- **Performance:** 95+
- **Accessibility:** 100
- **Best Practices:** 100
- **SEO:** 100

## Testing

### Unit Tests (Future)

```bash
pnpm test
```

### E2E Tests (Playwright)

```bash
# Install browsers
npx playwright install chromium

# Run E2E tests
pnpm test:e2e

# Run specific test
npx playwright test tests/e2e/smoke.spec.ts

# Debug mode
npx playwright test --debug
```

**Test structure:**

```
tests/e2e/
├── smoke.spec.ts                  # Basic smoke tests
├── extended/
│   ├── dashboard-tokens.spec.ts   # Token dashboard
│   ├── analysis-notifications.spec.ts  # WebSocket notifications
│   ├── codex-tagging.spec.ts      # Wallet tagging
│   └── ...                        # Other feature tests
├── fixtures/
│   └── api.fixture.ts             # Test fixtures
└── helpers/
    └── test-data.ts               # Test data generators
```

## Troubleshooting

### Common Issues

**Build errors:**
```bash
# Clean install
rm -rf node_modules .next
pnpm install
```

**Type errors:**
```bash
# Check for specific issues
pnpm type-check

# Sync API types if backend changed
pnpm sync-types:update
```

**WebSocket not connecting:**
- Verify backend is running on port 5003
- Check browser console for errors
- Ensure CORS is configured in backend
- Check firewall allows WebSocket connections

**Market cap not refreshing:**
- Check browser console for API errors
- Verify backend `/api/tokens/refresh-market-caps` endpoint is accessible
- Check backend rate limiting settings

**Wallet balances incorrect:**
- Backend uses real-time SOL/USD pricing from CoinGecko
- Ensure backend is updated to latest version
- Check that Helius API key is valid

**UI not updating after bulk operations:**
- Should auto-refresh; if not, manually reload page
- Check browser console for errors
- Verify WebSocket connection is active

**"Cannot find module 'jest-worker/processChild.js'" error:**
```bash
# Next.js build cache corruption
rm -rf node_modules .next
pnpm install
```

**Docker build fails:**
- Ensure `output: 'standalone'` is set in `next.config.ts`
- Check that all dependencies are in `package.json`
- Verify Node.js version in Dockerfile matches local

**CI checks failing:**
```bash
# Run CI checks locally
run_ci_checks.bat  # Windows
./run_ci_checks.sh # Unix

# Fix auto-fixable issues
pnpm lint:fix
pnpm format
```

### Debug Mode

Enable verbose logging:

```typescript
// In components or pages
console.log('Debug info:', data);

// In API client
import { debugLog } from '@/lib/debug';
debugLog('API call', { endpoint, data });
```

### Browser DevTools

**React DevTools:**
- Install React DevTools extension
- Inspect component tree
- View props and state
- Profile performance

**Network Tab:**
- Monitor API calls
- Check WebSocket connection
- Inspect request/response payloads

## Security

- **No API Keys in Frontend** - All sensitive data in backend
- **CORS Configuration** - Backend allows frontend origin
- **Input Validation** - All user input sanitized
- **XSS Protection** - React escapes output by default
- **HTTPS in Production** - TLS for all communications
- **Dependency Scanning** - Automated security checks

## License

MIT License - See ../../LICENSE file for details.

---

**Part of the Meridinate monorepo.** See [root README](../../README.md) for full project documentation.
