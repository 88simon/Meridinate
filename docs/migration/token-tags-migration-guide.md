# Token Tags Migration Guide

## Overview

This guide covers the token tagging system implementation that replaces the legacy `gem_status` field with a flexible, extensible tagging system.

## Database Changes

### New Table: `token_tags`

The `token_tags` table stores tags for tokens (e.g., "gem", "dud", "trending"):

```sql
CREATE TABLE IF NOT EXISTS token_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(token_id, tag),
    FOREIGN KEY (token_id) REFERENCES analyzed_tokens(id) ON DELETE CASCADE
)

CREATE INDEX IF NOT EXISTS idx_token_tags_token_id
ON token_tags(token_id)
```

### Automatic Migration

The database schema is automatically created on backend startup via `analyzed_tokens_db.init_database()`. No manual migration steps are required.

**To apply changes:**
1. Stop the backend server (if running)
2. Restart the backend server

The `token_tags` table will be created automatically if it doesn't exist.

## API Changes

### New Endpoints

**Get Token Tags**
```http
GET /api/tokens/{token_id}/tags
Response: {"tags": ["gem", "dud"]}
```

**Add Token Tag**
```http
POST /api/tokens/{token_id}/tags
Body: {"tag": "gem"}
Response: {"message": "Tag 'gem' added successfully"}
```

**Remove Token Tag**
```http
DELETE /api/tokens/{token_id}/tags
Body: {"tag": "gem"}
Response: {"message": "Tag 'gem' removed successfully"}
```

### Updated Endpoints

The following endpoints now include a `tags` array in their responses:
- `GET /api/tokens/history` - Each token includes `tags: string[]`
- `GET /api/tokens/{token_id}` - Token detail includes `tags: string[]`
- `GET /api/wallets/multi-token` - Uses tags to build `gem_statuses` array

### Legacy Endpoint (Deprecated)

The old `gem_status` endpoint still exists for backwards compatibility but is deprecated:
```http
POST /api/tokens/{token_id}/gem-status (DEPRECATED)
```

## Frontend Changes

### API Client Updates

New functions in `lib/api.ts`:
- `getTokenTags(tokenId)` - Get tags for a token
- `addTokenTag(tokenId, tag)` - Add a tag to a token
- `removeTokenTag(tokenId, tag)` - Remove a tag from a token

### UI Changes

**Token Table (`tokens-table.tsx`)**
- GEM/DUD buttons now use token tag endpoints
- Tags appear as badges next to token names
- Optimistic UI updates with error rollback

**Multi-Token Wallets Panel**
- GEM/DUD badges shown inline with token names
- Badges built from token tags, not `gem_status` field

## Cache Invalidation

Token tag operations invalidate two caches:
1. `tokens_history` - Token list cache
2. `multi_early_buyer_wallets` - Multi-token wallets cache

This ensures UI stays synchronized across both Token Table and Multi-Token Wallets panel.

## Troubleshooting

### Tags Not Syncing

**Symptom:** Changes to GEM/DUD tags don't appear in UI

**Solution:**
1. Hard refresh browser (Ctrl+Shift+R / Cmd+Shift+R)
2. Check browser console for errors
3. Verify backend logs show "Token tag added/removed" messages

### Database Table Missing

**Symptom:** 500 errors when accessing tag endpoints

**Solution:**
1. Check backend logs for "token_tags" table errors
2. Restart backend server to trigger automatic schema creation
3. Verify table exists:
   ```sql
   SELECT name FROM sqlite_master WHERE type='table' AND name='token_tags';
   ```

### Tags Not Persisting

**Symptom:** Tags disappear after browser refresh

**Solution:**
1. Check backend logs for database commit errors
2. Verify database file is writable
3. Check for disk space issues

## Testing

### Backend Tests

Run token tag tests:
```bash
cd apps/backend/src
../.venv/Scripts/python.exe -m pytest ../tests/routers/test_tokens.py::TestTokenTags -v
```

Expected: 10 tests pass

### Manual Testing

1. Open Token Table dashboard
2. Click GEM button on a token
3. Verify:
   - Button turns green
   - Badge appears next to token name
   - Multi-Token Wallets panel shows GEM badge
4. Click GEM again to clear
5. Verify badge disappears in both locations

## Migration from gem_status

If you have existing `gem_status` data, you can migrate it to token tags:

```python
import sqlite3

# Connect to database
conn = sqlite3.connect('apps/backend/data/db/analyzed_tokens.db')
cursor = conn.cursor()

# Migrate gem_status to token_tags
cursor.execute("""
    INSERT INTO token_tags (token_id, tag)
    SELECT id, gem_status
    FROM analyzed_tokens
    WHERE gem_status IS NOT NULL
    AND gem_status IN ('gem', 'dud')
    ON CONFLICT DO NOTHING
""")

conn.commit()
conn.close()
```

After migration, the `gem_status` field can be kept for backwards compatibility or removed in a future update.

## Rollback Plan

If you need to rollback to `gem_status`:

1. Update frontend to use `updateGemStatus()` instead of `addTokenTag()`/`removeTokenTag()`
2. Update backend to write to both `gem_status` field and `token_tags` table
3. Deploy changes
4. Optionally drop `token_tags` table after confirming rollback works

## Performance Considerations

- **Query optimization:** Tags are batch-fetched in one query per page load
- **Index coverage:** `idx_token_tags_token_id` index covers all tag lookups
- **Cache hit rate:** ETag-based caching reduces repeated queries

**Expected performance:**
- Tag fetch: <5ms (cached), <20ms (uncached)
- Tag add/remove: <50ms (includes cache invalidation)
- Token history with tags: <100ms for 100+ tokens

## Security

- **SQL injection:** All queries use parameterized statements
- **Rate limiting:** Tag endpoints use `READ_RATE_LIMIT` (100 req/min per IP)
- **Validation:** Tag names validated as non-empty strings
- **Authorization:** None currently - consider adding user-based tags in future

## Future Enhancements

Possible extensions to the tagging system:
1. User-specific tags (multi-tenant support)
2. Tag categories (classification, sentiment, custom)
3. Tag colors and icons
4. Bulk tag operations
5. Tag-based filtering and search
6. Tag analytics and trending tags

---

**Last Updated:** November 2025
**Related Docs:**
- [PROJECT_BLUEPRINT.md](../../PROJECT_BLUEPRINT.md) - Token Classification section
- [Backend README](../../apps/backend/README.md) - Token tag endpoints
- [Frontend README](../../apps/frontend/README.md) - Token Classification UI
