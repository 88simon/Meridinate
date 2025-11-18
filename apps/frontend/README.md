# Meridinate Web

[![CI](https://github.com/88simon/gun_del_sol_web/workflows/CI/badge.svg)](https://github.com/88simon/gun_del_sol_web/actions)
[![CodeQL](https://github.com/88simon/gun_del_sol_web/workflows/CodeQL%20Security%20Scan/badge.svg)](https://github.com/88simon/gun_del_sol_web/actions)
[![Node.js](https://img.shields.io/badge/node-22.x-brightgreen)](https://nodejs.org/)
[![pnpm](https://img.shields.io/badge/pnpm-9.x-orange)](https://pnpm.io/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-blue)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

Web dashboard for Meridinate - A Solana token analysis and monitoring tool.

## Overview

This is the frontend web interface for Meridinate, built with:

- Framework - [Next.js 15](https://nextjs.org/15)
- Language - [TypeScript](https://www.typescriptlang.org)
- Styling - [Tailwind CSS v4](https://tailwindcss.com)
- Components - [Shadcn-ui](https://ui.shadcn.com)
- Tables - [Tanstack Data Tables](https://ui.shadcn.com/docs/components/data-table)
- State Management - [Zustand](https://zustand-demo.pmnd.rs)
- Linting - [ESLint](https://eslint.org)
- Formatting - [Prettier](https://prettier.io)

## Features

- **Token Analysis Dashboard**: View and analyze Solana token data
- **Market Cap Tracking**: Dual market cap display (original at analysis time + current refreshed value)
  - Per-row refresh icons for individual token updates
  - Bulk refresh for all visible or selected tokens
  - Instant UI updates without page reload
  - Timestamps showing when market cap was last refreshed
  - Previous vs current comparison with color indicators (green ▲ increase, red ▼ decrease, gray = first refresh)
- **Wallet Balance Tracking**: Real-time wallet balance updates with accurate SOL/USD pricing
  - Column header refresh icon for bulk balance updates
  - Per-row refresh icons for individual wallet updates
  - Info tooltips showing API credit costs
  - Instant UI updates without page reload
- **Wallet Tracking**: Monitor early buyer wallets and their transactions
- **Historical Analysis**: View past token analysis runs with detailed wallet breakdowns
- **Real-time Updates**: Live data from the FastAPI backend API
- **Trash Management**: Soft-delete tokens with restore/permanent delete options
- **Solscan Settings Management**: Centralized control panel for Solscan URL parameters
  - Activity type dropdown (SPL Transfer, SOL Transfer, etc.)
  - Minimum value filter with arrow controls and drag-to-adjust
  - Page size selection (10, 20, 30, 40, 60, 100)
  - Auto-save after 300ms of changes
  - Dynamic URL generation for multi-token wallet hyperlinks
  - Syncs with AutoHotkey action wheel via INI file
- **Tags & Codex**
  - Nationality tag dropdown (US, CN, KR, JP, EU, UK, SG, IN, RU, BR, CA, AU), one per wallet
  - Codex panel shows token count per wallet (deleted tokens filtered)

## Getting Started

### Prerequisites

- Node.js 22+ installed
- pnpm 9+ installed (`npm install -g pnpm`)
- Meridinate backend running on `http://localhost:5003`

### Installation

1. Clone the repository:

```bash
git clone https://github.com/88simon/gun_del_sol_web.git
cd gun_del_sol_web
```

2. Install dependencies:

```bash
pnpm install
```

3. Start the development server:

```bash
pnpm dev
```

4. Open [http://localhost:3000](http://localhost:3000) in your browser

### Docker Setup (Recommended)

Run the full stack (backend + frontend) with Docker Compose:

```bash
# 1. Ensure backend config files exist in sibling repo
# See ../meridinate-backend/README.md for backend setup

# 2. Build and run with Docker Compose
docker-compose up -d

# 3. View logs
docker-compose logs -f frontend
docker-compose logs -f backend

# 4. Stop services
docker-compose down
```

**Frontend only (manual Docker build):**

```bash
docker build -t gun-del-sol-frontend .
docker run -d -p 3000:3000 \
  -e NEXT_PUBLIC_API_URL=http://localhost:5003 \
  -e NEXT_PUBLIC_SENTRY_DISABLED=true \
  gun-del-sol-frontend
```

The Docker image is automatically built and tested via GitHub Actions on every push to `main`.

## Project Structure

```
src/
├── app/                    # Next.js App Router
│   ├── dashboard/         # Dashboard pages
│   │   └── tokens/       # Token analysis pages
│   └── api/              # API routes
├── components/           # Shared components
│   ├── ui/              # UI components
│   └── layout/          # Layout components
├── lib/                 # Utilities
│   └── api.ts          # Backend API client
└── types/              # TypeScript types
```

## Backend Integration

This frontend connects to the Meridinate FastAPI backend. Make sure the backend is running on port 5003 before starting the frontend.

Backend repository: [meridinate-backend](https://github.com/88simon/meridinate-backend)

## Development & CI/CD

Meridinate Web includes comprehensive CI/CD pipelines with GitHub Actions:

- **Automated Testing:** ESLint (normal + strict), Prettier formatting checks, TypeScript type checking
- **Automated Builds:** Next.js build verification with artifact uploads
- **Security Scanning:** CodeQL analysis for JavaScript/TypeScript vulnerabilities
- **Docker Support:** Automated Docker image builds with SBOM generation and Trivy vulnerability scanning
- **Dependency Management:** Dependabot automatically creates PRs for package updates (grouped by category)

**Quick commands:**

```bash
# Install dependencies
pnpm install

# Run all CI checks locally (before pushing)
run_ci_checks.bat  # Windows
./run_ci_checks.sh # Unix/Linux/macOS

# Fix linting and formatting issues
pnpm lint:fix

# Type check
pnpm type-check

# Build for production
pnpm build

# Start production server
pnpm start
```

📚 **Documentation:**

- [CI/CD Enhancement Summary](.github/CI_CD_ENHANCEMENTS.md)
- [Branch Protection Guide](.github/BRANCH_PROTECTION.md)

## Troubleshooting

- **Build errors:** Run `pnpm install` to ensure dependencies are up to date
- **Type errors:** Check `pnpm type-check` output for specific issues
- **Docker build fails:** Ensure `output: 'standalone'` is set in `next.config.ts`
- **CI checks failing:** Run `run_ci_checks.bat` or `run_ci_checks.sh` locally to identify issues
- **Backend connection issues:** Verify backend is running on port 5003 and accessible
- **"Cannot find module 'jest-worker/processChild.js'" error:** This indicates Next.js build cache corruption. Fix with:
  ```bash
  rm -rf node_modules .next
  pnpm install
  ```
- **Market cap not refreshing:** Check browser console for API errors; verify backend is running and responsive
- **Wallet balances showing incorrect values:** Backend now uses real-time SOL/USD pricing from CoinGecko; ensure backend is updated to latest version
- **Balance refresh not working:** Check that backend `/wallets/refresh-balances` endpoint is accessible; verify Helius API key is valid
- **UI not updating after bulk operations:** This should auto-refresh; if not, manually refresh the page

## License

MIT License - see LICENSE file for details
