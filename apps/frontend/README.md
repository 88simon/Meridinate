# Meridinate Frontend

[![Node.js](https://img.shields.io/badge/node-22.x-brightgreen)](https://nodejs.org/)
[![pnpm](https://img.shields.io/badge/pnpm-10.x-orange)](https://pnpm.io/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-blue)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)

Modern Next.js dashboard for Meridinate – Solana token analysis and wallet monitoring.

## Overview

Production-ready React app:

- Next.js 15 (App Router, Turbopack) + TypeScript 5.7
- Tailwind CSS 4 + shadcn/ui
- TanStack Table v8 for data grids
- React hooks/Context, WebSockets for live updates
- ESLint + Prettier

## Features

Highlights (not exhaustive):

- Token dashboard with filtering, search, sorting, pagination.
- Market cap tracking (per-token and bulk refresh) with timestamps.
- Wallet balance tracking with trend indicators.
- Multi-Token Early Wallets: filters, smart search, sortable columns, compact layout, virtualization.
- Tagging (wallet tags, additional tags), GEM/DUD classification.
- Top holders modal + multi-token top-holder badge.
- SWAB tab for PnL/positions with webhook/reconciliation pipeline.
- Status bar with live credit tracking, recent events popover, polling + focus revalidation.
- Solscan settings synced with shared INI for AHK action wheel.
- **Batch API Endpoints** - Top holder badge counts use single batch request instead of N individual calls (98% bandwidth reduction)
- **Client-Side Refetch** - Replace router.refresh() with callbacks for instant updates without full page reload

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
│   │   ├── layout/             # Layout components (header, sidebar, dashboard-wrapper)
│   │   ├── master-control/     # Split settings modal (tab components, shared inputs)
│   │   ├── meridinate-logo.tsx # MeridinateLogo SVG component
│   │   ├── status-bar.tsx      # Bottom status bar with metrics
│   │   ├── wallet-tags.tsx     # Wallet tagging UI
│   │   ├── additional-tags.tsx # Additional tags (bot, whale, insider, gunslinger, gambler)
│   │   ├── forms/              # Form components
│   │   └── ...                 # Feature components
│   ├── lib/                    # Utilities
│   │   ├── api.ts              # Backend API client
│   │   ├── generated/          # Auto-generated types
│   │   │   └── api-types.ts    # OpenAPI TypeScript types
│   │   └── utils.ts            # Shared utilities
│   ├── hooks/                  # Custom React hooks
│   │   ├── useAnalysisNotifications.ts  # WebSocket hook
│   │   ├── useStatusBarData.ts # Status bar polling + focus revalidation
│   │   └── ...                 # Other hooks
│   ├── types/                  # TypeScript types
│   │   └── ingest-settings.ts  # Ingest settings (mirrors backend schema)
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

**Resilient Fetching:** API calls use `fetchWithRetry` utility with 12s timeout, 2 retries, and exponential backoff (1s, 2s delays). This prevents UI blocking when the backend is busy with long-running operations like ingestion jobs.

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

1. **CSS Transitions for Animations**

   - All interactive transitions use native CSS (Framer Motion libs remain in package.json but are no longer imported)
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
