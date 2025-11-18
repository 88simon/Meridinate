# API Types Synchronization

This document describes the automated OpenAPI→TypeScript types synchronization system between the backend and frontend repositories.

## Overview

The Meridinate project uses a FastAPI backend that automatically generates TypeScript types from its OpenAPI schema. These types are automatically synced to the frontend to ensure type safety across the full stack.

## Architecture

### Backend (Meridinate Backend)

- **Workflow:** `.github/workflows/openapi-schema.yml`
- **Generated files:**
  - `backend/openapi.json` - OpenAPI 3.0 schema
  - `backend/api-types.ts` - TypeScript types (committed to backend repo)
  - Frontend: `src/lib/generated/api-types.ts` - Auto-synced types (committed to frontend repo)

### Frontend (Meridinate Frontend)

- **Workflow:** `.github/workflows/ci.yml` (api-types-check job)
- **Script:** `scripts/sync-api-types.ts`
- **Location:** `src/lib/generated/api-types.ts`

## How It Works

### 1. Automatic Sync (Backend → Frontend)

When changes are pushed to the `main` branch of the **backend** repository:

1. **Export OpenAPI Schema** - The FastAPI app's OpenAPI schema is exported to `backend/openapi.json`
2. **Generate TypeScript Types** - Using `openapi-typescript`, generates `backend/api-types.ts`
3. **Commit to Backend** - Types are committed to the backend repository
4. **Sync to Frontend** - Types are copied to `src/lib/generated/api-types.ts` in the frontend repository
5. **Create PR** - A pull request is created in the frontend repository with the updated types
6. **Merge PR** - After CI passes, merge the PR to update types in frontend

**Required:** The backend workflow needs a `FRONTEND_SYNC_TOKEN` secret with permissions to create PRs in the frontend repository. If not available, it falls back to the default `github.token`.

### 2. CI Guard (Frontend)

Every PR to the **frontend** repository runs a sync check:

1. Checks out frontend repository
2. **Extracts backend commit SHA** from the header of committed `src/lib/generated/api-types.ts`
3. Checks out the **specific backend commit** that generated those types (not latest main)
4. Generates fresh TypeScript types from that backend commit's OpenAPI schema
5. Compares with the committed `src/lib/generated/api-types.ts`
6. **Fails the CI** if types are out of sync

**Key Feature: Commit Pinning** - The CI compares against the exact backend version that generated the current types, preventing false failures when backend main advances.

### 3. Manual Sync (Development)

During local development, you can manually sync types using:

```bash
# Check if types are in sync
pnpm sync-types:check

# Update types from backend
pnpm sync-types:update
```

**Requirements:**

- Backend repository must be at `../backend` (relative to frontend root)
- Python 3.11+ with backend dependencies installed
- Node.js 20+ with pnpm

## Scripts & Commands

### Frontend Scripts

```json
{
  "sync-types": "tsx scripts/sync-api-types.ts",
  "sync-types:check": "tsx scripts/sync-api-types.ts",
  "sync-types:update": "tsx scripts/sync-api-types.ts --update"
}
```

### sync-api-types.ts

**Environment Variables:**

- `BACKEND_REPO_PATH` - Path to backend repository (default: `../backend`)
- `CI` - Set to `true` in CI environments

**Behavior:**

- **Check mode** (default): Validates types are in sync, exits with code 1 if not
- **Update mode** (`--update`): Regenerates and updates the committed types

## Workflow Details

### Backend: openapi-schema.yml

**Triggers:**

- Push to `main` branch
- Pull requests to `main`
- Manual workflow dispatch

**Jobs:**

1. **export-schema** - Exports OpenAPI schema, uploads artifact, comments on PRs
2. **generate-typescript** - (Only on main branch) Generates types and syncs to frontend

**Permissions:**

- `contents: write` - Required to commit generated types
- `pull-requests: write` - Required to comment on PRs

### Frontend: ci.yml

**New Job: api-types-check**

Runs in parallel with other CI jobs (lint, type-check, build).

**Steps:**

1. Checkout frontend repo to `frontend-repo/`
2. Checkout backend repo to `backend-repo/`
3. Setup Python + pnpm
4. Install dependencies for both repos
5. Create backend test config files
6. Run `pnpm sync-types:check` with custom backend path

**Dependencies:**

- Build job depends on: `[lint-format, type-check, api-types-check]`
- All checks must pass before PR can be merged

## File Structure

```
backend/ (Meridinate backend)
├── .github/
│   └── workflows/
│       └── openapi-schema.yml    # Auto-sync workflow
├── backend/
│   ├── openapi.json              # Generated schema
│   ├── api-types.ts              # Generated types (committed)
│   └── app/
│       └── main.py               # FastAPI app

meridinate-frontend/ (frontend)
├── .github/
│   ├── workflows/
│   │   └── ci.yml                # CI guard included
│   └── API_TYPES_SYNC.md         # This file
├── scripts/
│   └── sync-api-types.ts         # Manual sync script
└── src/
    └── lib/
        ├── generated/
        │   └── api-types.ts      # Auto-synced types (committed)
        └── api.ts                # API client using types
```

## Migration Guide

### Migrating from Manual Types

If you currently have manual TypeScript interfaces in `src/lib/api.ts`:

1. **Generate initial types:**

   ```bash
   pnpm sync-types:update
   ```

2. **Import generated types:**

   ```typescript
   // Before (manual types)
   export interface Token {
     id: number;
     token_address: string;
     // ...
   }

   // After (generated types)
   import { components } from './generated/api-types';

   export type Token = components['schemas']['Token'];
   ```

3. **Update API client:**

   - Replace manual interfaces with generated types
   - Use `paths` for request/response types
   - Use `components['schemas']` for model types

4. **Commit changes:**
   ```bash
   git add src/lib/generated/api-types.ts src/lib/api.ts
   git commit -m "feat: migrate to auto-generated API types"
   ```

### Example Usage

```typescript
import { components, paths } from './generated/api-types';

// Schema types
type Token = components['schemas']['Token'];
type TokensResponse = components['schemas']['TokensResponse'];

// Endpoint types
type GetTokensResponse =
  paths['/api/tokens/history']['get']['responses']['200']['content']['application/json'];
type GetTokenByIdParams =
  paths['/api/tokens/{id}']['get']['parameters']['path'];

// Use in API client
export async function getTokens(): Promise<TokensResponse> {
  const res = await fetch(`${API_BASE_URL}/api/tokens/history`);
  return res.json();
}
```

## Troubleshooting

### CI Failing: "API types are out of sync"

**Cause:** The committed types don't match the backend's current OpenAPI schema.

**Solution:**

```bash
# In frontend repo
pnpm sync-types:update
git add src/lib/generated/api-types.ts
git commit -m "chore: sync API types from backend"
git push
```

### Backend Workflow Not Syncing to Frontend

**Possible causes:**

1. Missing `FRONTEND_SYNC_TOKEN` secret → Check repository secrets
2. Token lacks push permissions → Verify token scopes
3. Frontend repo path incorrect → Check workflow checkout step

### Local Sync Script Fails

**Error: "Backend repository not found"**

- Ensure backend is cloned at `../backend`
- Or set `BACKEND_REPO_PATH` environment variable:
  ```bash
  BACKEND_REPO_PATH=/path/to/backend pnpm sync-types:update
  ```

**Error: "Failed to generate OpenAPI schema"**

- Ensure Python dependencies are installed:
  ```bash
  cd C:Meridinatebackendbackend/backend
  pip install -r requirements-dev.txt
  ```

## Commit Pinning System

### How It Works

The type sync system uses **commit pinning** to ensure consistency between frontend types and backend schema:

1. **Backend generates types** - When types are generated, a header comment is added:

   ```typescript
   /**
    * Auto-generated TypeScript types from Backend OpenAPI schema
    * Backend Commit: 52a736334365de52d56204117a50725a0de5c7cb
    * Generated: 2025-11-14 17:42:31 UTC
    * DO NOT EDIT - This file is auto-generated
    */
   ```

2. **Frontend CI extracts commit** - The frontend workflow extracts the backend commit SHA from this header

3. **Checkout pinned commit** - Instead of checking out latest backend `main`, the workflow checks out the specific commit that generated the types

4. **Compare against pinned version** - Types are regenerated from that pinned commit and compared

### Benefits

- **No false failures** - Backend changes won't break frontend PRs that are based on an earlier backend version
- **Predictable CI** - CI results are deterministic and reproducible
- **Gradual updates** - Frontend can update types at its own pace via `pnpm sync-types:update`

### Example Scenario

**Without commit pinning (old behavior):**

1. Frontend PR created (types based on backend commit `abc123`)
2. Backend merges new feature (now at commit `def456`)
3. Frontend CI runs, checks out backend `main` (`def456`)
4. CI fails because types don't match the new backend schema
5. Frontend must resync types before merging

**With commit pinning (new behavior):**

1. Frontend PR created (types based on backend commit `abc123`, SHA embedded in header)
2. Backend merges new feature (now at commit `def456`)
3. Frontend CI runs, extracts `abc123` from types header, checks out that commit
4. CI passes because comparison is against the correct backend version
5. Frontend can merge without forced resync (though eventual sync is still recommended)

## Security Considerations

### GitHub Token Permissions

The `FRONTEND_SYNC_TOKEN` should have:

- **Scope:** `repo` (full repository access)
- **Permissions:** `contents: write`
- **Expiry:** Set appropriate expiration (90 days recommended)

### Avoiding Infinite Loops

The workflows are designed to avoid triggering each other:

- Backend workflow only runs on main branch pushes/PRs
- Frontend commits from bot don't trigger workflows (uses `github-actions[bot]` user)
- If issues occur, check workflow triggers and add `if` conditions

## Future Enhancements

Potential improvements to the system:

1. **Versioning:** Track API version in types file header
2. **Changelog:** Auto-generate API changes in PR comments
3. **Breaking Changes:** Detect breaking changes and require confirmation
4. **Validation:** Add runtime validation using zod schemas generated from OpenAPI
5. **Monitoring:** Track sync frequency and failures in dashboards

## References

- [openapi-typescript](https://github.com/drwpow/openapi-typescript) - Type generation tool
- [FastAPI OpenAPI](https://fastapi.tiangolo.com/advanced/extending-openapi/) - Backend schema generation
- [GitHub Actions Workflows](https://docs.github.com/en/actions/using-workflows) - CI/CD automation

---

**Last Updated:** November 2025
**Maintainer:** 88simon
