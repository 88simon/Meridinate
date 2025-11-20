# GitHub Actions Workflows

This directory contains CI/CD workflows for the Meridinate monorepo.

## Workflows

### `monorepo-ci.yml`

Main CI pipeline for the entire monorepo. Runs on pushes and pull requests to `main` and `develop` branches.

**Jobs:**

1. **backend-tests** - Runs pytest for Python backend
   - Installs dependencies including new async task handling libraries (arq, redis, slowapi)
   - Creates test configuration files
   - Runs all backend tests with rate limiting disabled
   - Verifies new dependencies are properly installed

2. **frontend-lint** - Lints and checks formatting for Next.js frontend
   - ESLint checks
   - Prettier formatting validation

3. **frontend-typecheck** - TypeScript type checking for frontend
   - Runs `pnpm type-check`

4. **api-types-sync** - Validates API type synchronization
   - Generates OpenAPI schema from backend
   - Generates TypeScript types
   - Ensures frontend types match backend schema

5. **frontend-build** - Builds Next.js application
   - Depends on lint, typecheck, and API types sync passing
   - Uploads build artifact for verification

6. **all-checks** - Summary job
   - Reports status of all jobs
   - Creates PR comments with results
   - Fails if any critical check fails

## Legacy Workflows

The `apps/frontend/.github/workflows/` directory contains legacy workflows from before the monorepo migration. These may be consolidated or deprecated in favor of the root-level monorepo workflows.

**Note:** The monorepo CI does not currently include E2E tests. E2E testing with Playwright is still handled by the frontend-specific workflow if needed.

## Environment Variables

The backend tests run with:
- `RATE_LIMIT_ENABLED=false` - Disables rate limiting for tests
- `REDIS_ENABLED=false` - Uses in-memory storage instead of Redis for tests

## New Dependencies

The CI workflow now includes and validates:
- **arq** (>=0.26.0) - Async task queue
- **redis** (>=5.0.0,<6.0.0) - Redis client with hiredis for performance
- **slowapi** (>=0.1.9) - Rate limiting for FastAPI

These dependencies are verified in the backend-tests job to ensure they're properly installed and importable.
