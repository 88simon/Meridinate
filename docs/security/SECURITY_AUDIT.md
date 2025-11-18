# OPSEC Security Audit

**Status:** Critical. Wallets, token addresses, and API keys can still leak through logs and unauthenticated routes if the backend is run with defaults.

## Summary of Findings

| Severity | Issue | Status |
| --- | --- | --- |
| Critical | Wallet and token addresses appear in `print()` statements inside `backend/api_service.py` and `backend/helius_api.py`. | Outstanding |
| Critical | API endpoints allow anyone on the machine to mutate data without authentication. | Outstanding |
| High | Browser `console.log` calls in dashboard templates echo sensitive payloads. | Outstanding |
| Medium | Detailed error messages bubble up to API callers. | Outstanding |

## Immediate Controls (10 minutes)

1. **Production logging switch**
   - In both `backend/api_service.py` and `backend/helius_api.py`, wrap `print` with the helper from `secure_logging.py` or gate raw prints behind `DEBUG_LOGGING = False`.
   - Verify `debug_config.py` defaults to `DEBUG_MODE = False`.

2. **Disable browser logs**
   - Near the top of each dashboard script block, add:
     ```javascript
     const DEBUG = false;
     const originalLog = console.log;
     console.log = (...args) => {
         if (DEBUG) originalLog(...args);
     };
     ```

3. **Sanitize error responses**
   - Replace `return jsonify({"error": str(e)}), 500` with `log_error(...)` plus `return jsonify({"error": "An error occurred"}), 500`.

These changes stop accidental leaks while you apply the long-term fixes below.

## Required Fixes

### 1. Replace Sensitive Prints With Structured Logging

- Use the helpers from `secure_logging.py` everywhere:
  - `log_address_registered`, `log_address_removed`
  - `log_analysis_start`, `log_analysis_complete`
  - `log_success`, `log_warning`, `log_error`
- Never log full wallet addresses or mint addresses. If you need context, keep only the first 4 and last 4 characters.

**Audit targets:**
- `backend/api_service.py`: routes `/register`, `/remove`, `/analysis/*`, `/api/tokens/*`, webhook helpers.
- `backend/helius_api.py`: token metadata fetch, transaction iterators, debug traces.

### 2. Add API Authentication

1. Define a decorator in `backend/api_service.py`:
   ```python
   from functools import wraps
   API_KEY = os.environ.get("GUN_API_KEY") or "CHANGE_ME"

   def require_api_key(func):
       @wraps(func)
       def wrapper(*args, **kwargs):
           provided = request.headers.get("X-API-Key")
           if provided != API_KEY:
               return jsonify({"error": "Unauthorized"}), 401
           return func(*args, **kwargs)
       return wrapper
   ```
2. Apply it to every mutating route (`POST /register`, `/analysis`, `/import`, `/clear`, etc.).
3. Store the secret in `backend/config.json` and surface it to the action wheel or frontend via environment variables.

### 3. Hide Stack Traces

- Wrap every route body with `try`/`except`.
- Log `type(e).__name__` plus a sanitized message, return a generic response.
- Ensure Werkzeug/Flask debug mode is off in production (`socketio.run(..., debug=False)`).

### 4. Browser Console Hygiene

- Remove or guard `console.log`/`console.table` calls inside `templates/` or frontend components that print wallet arrays.
- Use a `DEBUG` flag tied to your `debug_config.get_debug_js_flag()` endpoint.

### 5. Temp Files and Exports

- Confirm all exports live under `backend/analysis_results/` or `backend/axiom_exports/`. Never write to `%TEMP%`.
- Keep the folders git-ignored (already enforced) and periodically clear stale exports if you share screens.

## Configuration Hardening

Create `backend/config.json` with explicit production flags:

```json
{
  "helius_api_key": "REPLACE_ME",
  "api_key": "GENERATE_A_RANDOM_VALUE",
  "debug_logging": false,
  "debug_transactions": false
}
```

Load these settings inside `api_service.py` and `helius_api.py` before initializing logging.

## Verification Checklist

- [ ] `rg -n "print\(.*address"` returns no matches outside of gated debug blocks.
- [ ] No route returns stack traces or mentions filesystem paths.
- [ ] Every mutating route returns 401 when `X-API-Key` is missing.
- [ ] Browser console stays empty while running through a workflow.
- [ ] `backend/analysis_results/` and `backend/axiom_exports/` never leave the machine.

## Emergency Procedure

If you suspect data already leaked:
1. Delete all log files.
2. Rotate API keys immediately.
3. Treat any exposed wallet addresses as compromised and adjust your trading strategy.
4. Re-clone a clean repo once secrets are rotated.

---

Re-run this audit whenever you touch logging, add new routes, or change deployment targets. Nothing leaves the local box unless you explicitly paste it somewhere—keep it that way.
