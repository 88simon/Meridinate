# E2E Testing Suite

Comprehensive end-to-end test suite for Gun Del Sol using Playwright.

## Overview

This test suite covers all major features of the Gun Del Sol frontend application, testing the integration between the Next.js frontend (port 3000) and FastAPI backend (port 5003).

## Test Suites

### Smoke Tests (Fast - CI Default)

- **Location**: `smoke.spec.ts`
- **Runtime**: ~10 seconds
- **Tests**: 3 basic validation tests
- **Purpose**: Quick validation that critical pages load
- **Run**: `pnpm test:e2e`
- **CI**: Runs automatically (non-blocking)

### Extended Tests (Comprehensive - Manual)

- **Location**: `extended/*.spec.ts`
- **Runtime**: ~5 minutes
- **Tests**: 60+ comprehensive feature tests
- **Purpose**: Full feature validation and regression testing
- **Run**: `pnpm test:e2e:extended`
- **CI**: Manual only (not in automated pipelines)

**Recommendation**: Run smoke tests frequently, extended tests before major releases.

## Test Coverage

### Feature Tests

1. **Dashboard Tokens Panel** (`dashboard-tokens.spec.ts`)

   - Token list display
   - Token details modal
   - Token history view
   - Wallet type display (creator, holder, dev, insider, sniper)
   - Soft delete operation

2. **Multi-Token Wallets Panel** (`multi-token-wallets.spec.ts`)

   - Display wallets holding multiple tokens
   - Refresh balances functionality
   - Wallet sorting and filtering
   - Token count display

3. **Watchlist Registration** (`watchlist.spec.ts`)

   - Register single address
   - Import multiple addresses
   - View watchlist
   - Remove address from watchlist
   - Clear entire watchlist
   - Label management

4. **Trash View Operations** (`trash-view.spec.ts`)

   - View trashed tokens
   - Restore token from trash
   - Permanently delete token
   - Bulk operations
   - Empty trash state

5. **Codex Tagging System** (`codex-tagging.spec.ts`)

   - Add tag to wallet
   - Remove tag from wallet
   - Batch tag operations
   - View Codex drawer
   - Filter wallets by tag
   - Tag autocomplete

6. **Analysis Notifications (WebSocket)** (`analysis-notifications.spec.ts`)
   - WebSocket connection establishment
   - Job queued notification
   - Job started notification
   - Job completed notification
   - Job failed notification
   - Notification UI display

## Running Tests

### Local Development

```bash
# Run all E2E tests (headless)
pnpm test:e2e

# Run tests in headed mode (see browser)
pnpm test:e2e:headed

# Run tests in UI mode (interactive)
pnpm test:e2e:ui

# Run tests in debug mode
pnpm test:e2e:debug

# View test report
pnpm test:e2e:report
```

### Prerequisites

The tests expect both the backend and frontend to be running:

- **Backend**: FastAPI server on `http://localhost:5003`
- **Frontend**: Next.js app on `http://localhost:3000`

Playwright will automatically start these servers via the webServer configuration in `playwright.config.ts`.

## CI/CD Integration

Tests run automatically in GitHub Actions CI on:

- Push to `main` or `develop` branches
- Pull requests to `main` or `develop` branches
- Manual workflow dispatch

The CI workflow:

1. Checks out both frontend and backend repos
2. Sets up Python and Node.js environments
3. Installs dependencies
4. Starts backend and frontend servers
5. Runs E2E tests
6. Uploads Playwright reports and test results as artifacts

## Test Structure

```
tests/e2e/
├── fixtures/
│   └── api.fixture.ts       # API interaction helpers
├── helpers/
│   └── test-data.ts         # Test data and utility functions
├── extended/                # Extended tests (manual only)
│   ├── dashboard-tokens.spec.ts
│   ├── multi-token-wallets.spec.ts
│   ├── watchlist.spec.ts
│   ├── trash-view.spec.ts
│   ├── codex-tagging.spec.ts
│   └── analysis-notifications.spec.ts
├── smoke.spec.ts            # Smoke tests (CI default)
└── README.md
```

## Configuration

Test configuration is in `playwright.config.ts`:

- **Base URL**: `http://localhost:3000`
- **Timeout**: 30 seconds per test
- **Retries**: 2 in CI, 0 locally
- **Browsers**: Chromium (can be extended to Firefox, WebKit)
- **Parallel execution**: Enabled
- **Screenshots**: On failure
- **Videos**: On failure
- **Traces**: On first retry

## Test Data

Sample Solana addresses and test data are defined in `helpers/test-data.ts`:

- USDC token address
- SOL address
- Sample wallet addresses (non-real for testing)
- Sample tags (whale, dev, suspicious, etc.)

## API Fixtures

The `api.fixture.ts` provides helpers for:

- Health checks
- Database cleanup
- Token seeding
- Watchlist management
- Tag operations

## Writing New Tests

1. Create a new `.spec.ts` file in `tests/e2e/`
2. Import fixtures and helpers:
   ```typescript
   import { test, expect } from '@playwright/test';
   import { apiFixture } from './fixtures/api.fixture';
   import { SAMPLE_ADDRESSES, waitFor } from './helpers/test-data';
   ```
3. Write test suites using `test.describe()` and `test()`
4. Use `data-testid` attributes for reliable element selection
5. Clean up test data in `beforeEach` and `afterEach` hooks

## Best Practices

- ✅ Use `data-testid` attributes for element selection
- ✅ Wait for explicit conditions, not arbitrary timeouts
- ✅ Clean up test data between tests
- ✅ Use fixtures for reusable setup/teardown
- ✅ Test user flows, not implementation details
- ✅ Keep tests independent and isolated
- ❌ Don't rely on test execution order
- ❌ Don't use hardcoded waits (except for API operations)
- ❌ Don't test UI styling details

## Debugging Tests

### Local Debugging

```bash
# Run in debug mode (opens Playwright Inspector)
pnpm test:e2e:debug

# Run specific test file
npx playwright test tests/e2e/dashboard-tokens.spec.ts

# Run tests matching a title
npx playwright test --grep "should display tokens table"
```

### CI Debugging

When tests fail in CI:

1. Check the **Actions** tab in GitHub
2. Download the **playwright-report** artifact
3. Extract and open `index.html` in a browser
4. Review screenshots, videos, and traces

## Troubleshooting

### Common Issues

**Backend not starting:**

- Check if port 5003 is already in use
- Verify Python dependencies are installed
- Check backend logs in CI artifacts

**Frontend not starting:**

- Check if port 3000 is already in use
- Verify pnpm dependencies are installed
- Check `pnpm dev` runs successfully

**Tests timing out:**

- Increase timeout in specific tests
- Check network conditions
- Verify backend responses are fast enough

**Flaky tests:**

- Add explicit waits for asynchronous operations
- Use `waitForLoadState('networkidle')`
- Retry failed tests to identify patterns

## Maintenance

- Update test data when backend schemas change
- Add new test files for new features
- Update fixtures when API endpoints change
- Keep Playwright version up to date
- Review and update selectors if UI changes

## Resources

- [Playwright Documentation](https://playwright.dev/docs/intro)
- [Best Practices](https://playwright.dev/docs/best-practices)
- [Debugging Guide](https://playwright.dev/docs/debug)
- [CI Configuration](https://playwright.dev/docs/ci)
