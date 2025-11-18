# Quick OPSEC Fixes

Need a safe build in under ten minutes? Apply the controls below before sharing screens, collecting logs, or letting anyone else touch the backend.

## 1. Disable Verbose Logging

Add the production guard near the top of **both** `backend/api_service.py` and `backend/helius_api.py`:

```python
from secure_logging import log_error, log_info, log_success, log_warning

DEBUG_LOGGING = False  # flip to True only when debugging locally

def safe_print(*args, **kwargs):
    if DEBUG_LOGGING:
        print(*args, **kwargs)

print = safe_print
```

Replace any remaining raw `print()` calls that output wallet or token data with the structured helpers so they honor the flag.

## 2. Silence Browser Consoles

Drop this snippet at the top of each dashboard script bundle (or Next.js layout):

```javascript
const DEBUG = false;
const originalLog = console.log;
console.log = (...args) => {
    if (DEBUG) {
        originalLog(...args);
    }
};
```

Toggle `DEBUG` only when capturing traces on an air-gapped machine.

## 3. Generic API Errors

Wrap every route in `backend/api_service.py` with a `try`/`except` that returns:

```python
except Exception as exc:
    log_error(f"Route failed: {type(exc).__name__}")
    return jsonify({"error": "An error occurred"}), 500
```

This stops stack traces and file paths from reaching API clients.

## 4. Minimum Authentication

Even on localhost, lock down mutating routes with a single API key:

```python
API_KEY = os.environ.get("GUN_API_KEY") or "CHANGE_ME"

def require_api_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if request.headers.get("X-API-Key") != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return func(*args, **kwargs)
    return wrapper
```

Add `@require_api_key` to `/register`, `/analysis`, `/import`, `/clear`, and `/api/settings`.

## 5. Test Before Use

1. Restart the backend (`start_backend.bat`).
2. Register a wallet and launch an analysis job.
3. Confirm the console shows only sanitized log lines and the browser console stays empty.
4. Hit a protected route without `X-API-Key` and expect `401 Unauthorized`.

These steps do not replace the full audit in `SECURITY_AUDIT.md`, but they dramatically reduce accidental leakage while you work through the deeper fixes.
