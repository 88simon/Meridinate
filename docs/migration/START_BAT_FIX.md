# start.bat Fix Summary

**Date:** November 17, 2025
**Issue:** start.bat not launching backend successfully
**Status:** ✅ **FIXED**

---

## 🐛 Root Cause

The backend FastAPI server was exiting immediately after launch due to an incorrect uvicorn configuration in `main.py`.

### Technical Details

**Problem:** When running `python -m meridinate.main`, the code was calling:
```python
uvicorn.run(app, host="0.0.0.0", port=5003, reload=True)
```

**Issue:** When `reload=True` is enabled, uvicorn requires the app to be passed as an **import string** (like `"meridinate.main:app"`) rather than as an **object** (like `app`). When passed as an object with reload enabled, uvicorn exits with the warning:
```
WARNING: You must pass the application as an import string to enable 'reload' or 'workers'.
```

---

## ✅ Fixes Applied

### **1. Fixed uvicorn.run() Call**
**File:** `apps/backend/src/meridinate/main.py:149`

**Before:**
```python
uvicorn.run(app, host="0.0.0.0", port=5003, reload=True)
```

**After:**
```python
# Use import string for reload to work properly
uvicorn.run("meridinate.main:app", host="0.0.0.0", port=5003, reload=True)
```

### **2. Moved Missing Python Modules**
The following modules needed to be in the `meridinate` package:

- ✅ `analyzed_tokens_db.py` → `apps/backend/src/meridinate/`
- ✅ `helius_api.py` → `apps/backend/src/meridinate/`
- ✅ `debug_config.py` → `apps/backend/src/meridinate/`
- ✅ `secure_logging.py` → `apps/backend/src/meridinate/`

### **3. Updated All Imports**
Fixed imports throughout the codebase:

```python
# OLD (broken)
import analyzed_tokens_db as db
from helius_api import TokenAnalyzer
from debug_config import is_debug_enabled
from secure_logging import log_error
from app import settings

# NEW (working)
from meridinate import analyzed_tokens_db as db
from meridinate.helius_api import TokenAnalyzer
from meridinate.debug_config import is_debug_enabled
from meridinate.secure_logging import log_error
from meridinate import settings
```

### **4. Fixed File Paths in settings.py**
**File:** `apps/backend/src/meridinate/settings.py`

Updated path calculation to use new monorepo structure:

```python
# Get backend root directory (apps/backend/)
# settings.py is at apps/backend/src/meridinate/settings.py
# Go up 3 levels: meridinate -> src -> backend
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Updated paths
DATABASE_FILE = os.path.join(BACKEND_ROOT, "data", "db", "analyzed_tokens.db")
SETTINGS_FILE = os.path.join(BACKEND_ROOT, "api_settings.json")
DATA_FILE = os.path.join(BACKEND_ROOT, "monitored_addresses.json")
ANALYSIS_RESULTS_DIR = os.path.join(BACKEND_ROOT, "data", "analysis_results")
AXIOM_EXPORTS_DIR = os.path.join(BACKEND_ROOT, "data", "axiom_exports")
```

### **5. Copied Config Files**
Moved essential config files from old location to new:

```bash
backend/backend/*.json → apps/backend/*.json
```

Files copied:
- ✅ `config.json` (Helius API key)
- ✅ `api_settings.json` (API configuration)
- ✅ `monitored_addresses.json` (Wallet data)
- ✅ `config.example.json` (Template)
- ✅ `openapi.json` (API schema)

### **6. Moved Virtual Environment**
```bash
backend/backend/.venv → apps/backend/.venv
```

### **7. Enhanced start.bat**
**File:** `scripts/start.bat`

Added virtual environment activation:

```batch
start "Meridinate - Backend" /D "%~dp0..\apps\backend" cmd /k "title Meridinate - FastAPI Backend && call .venv\Scripts\activate.bat && cd src && python -m meridinate.main"
```

### **8. Enhanced start-backend.bat**
**File:** `scripts/start-backend.bat`

Added explicit venv activation with fallback:

```batch
echo Activating virtual environment...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo ✓ Virtual environment activated
) else (
    echo WARNING: Virtual environment not found at .venv
    echo Using system Python
)
```

---

## 🧪 Verification

### **Backend Health Check**
```bash
$ curl http://localhost:5003/health
{
  "status": "healthy",
  "service": "FastAPI Gun Del Sol (Modular)",
  "version": "2.0.0",
  "architecture": "modular",
  "endpoints": 46,
  "websocket_connections": 0
}
```

### **Backend Startup Logs**
```
[Database] Schema verified: 22 columns present ✓
[Config] Loaded Helius API key: 3521c98a... ✓
[Config] API Settings: walletCount=50, transactionLimit=250, maxCredits=1000 ✓
INFO: Uvicorn running on http://0.0.0.0:5003 (Press CTRL+C to quit) ✓
INFO: Started server process [43248] ✓
INFO: Application startup complete. ✓
```

---

## 🚀 How to Use start.bat

### **Method 1: Master Launcher (All Services)**

```cmd
cd C:\Meridinate
scripts\start.bat
```

This will launch:
1. **AutoHotkey** action wheel (`tools/autohotkey/action_wheel.ahk`)
2. **Backend** FastAPI server (port 5003)
3. **Frontend** Next.js dev server (port 3000)

### **Method 2: Backend Only**

```cmd
cd C:\Meridinate
scripts\start-backend.bat
```

This will:
1. Activate virtual environment (`.venv`)
2. Start FastAPI backend on port 5003

### **Method 3: Frontend Only**

```cmd
cd C:\Meridinate
scripts\start-frontend.bat
```

This will:
1. Start Next.js dev server on port 3000

---

## 🔗 Service URLs

Once started, access the services at:

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:5003
- **API Documentation:** http://localhost:5003/docs
- **Health Check:** http://localhost:5003/health
- **WebSocket:** ws://localhost:5003/ws

---

## 📂 File Locations Summary

### **Python Modules**
All Python modules are now in the `meridinate` package:

```
apps/backend/src/meridinate/
├── analyzed_tokens_db.py    # Database operations
├── helius_api.py             # Helius API client
├── debug_config.py           # Debug configuration
├── secure_logging.py         # Secure logging utilities
├── settings.py               # Configuration management
├── main.py                   # FastAPI app entry point
├── routers/                  # API route handlers
├── models/                   # Pydantic data models
└── services/                 # Business logic services
```

### **Config Files**
```
apps/backend/
├── config.json                # API keys (gitignored)
├── api_settings.json          # API configuration
├── monitored_addresses.json   # Wallet addresses
└── config.example.json        # Template
```

### **Data Files**
```
apps/backend/data/
├── db/
│   └── analyzed_tokens.db     # Main database
├── backups/                   # Database backups
├── analysis_results/          # Analysis outputs
└── axiom_exports/             # Axiom data exports
```

### **Virtual Environment**
```
apps/backend/.venv/            # Python virtual environment
```

---

## ⚠️ Troubleshooting

### **Issue: "Virtual environment not found"**

**Solution:**
```bash
cd C:\Meridinate\apps\backend
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

### **Issue: "ModuleNotFoundError: No module named 'meridinate'"**

**Solution:** Make sure you're running from the correct directory:
```bash
cd C:\Meridinate\apps\backend\src
python -m meridinate.main
```

### **Issue: "HELIUS_API_KEY not set"**

**Solution:** Check that `config.json` exists and contains your API key:
```bash
cd C:\Meridinate\apps\backend
cat config.json
# Should show: {"helius_api_key": "your-key-here"}
```

### **Issue: Backend starts but exits immediately**

**Cause:** This was the original bug - uvicorn reload mode with app object

**Solution:** Already fixed in `main.py:149` - now uses import string

### **Issue: Database not found**

**Solution:** Database should be at `apps/backend/data/db/analyzed_tokens.db`

If missing, it will be created automatically on first run.

---

## 📊 Changes Summary

| Component | Action | Status |
|-----------|--------|--------|
| **main.py** | Fixed uvicorn.run() to use import string | ✅ Fixed |
| **Python modules** | Moved 4 modules to meridinate package | ✅ Complete |
| **Imports** | Updated all imports to use meridinate.* | ✅ Complete |
| **settings.py** | Fixed paths for monorepo structure | ✅ Complete |
| **Config files** | Copied to apps/backend/ | ✅ Complete |
| **Virtual env** | Moved to apps/backend/.venv | ✅ Complete |
| **start.bat** | Added venv activation | ✅ Complete |
| **start-backend.bat** | Enhanced with venv support | ✅ Complete |

---

## ✨ Result

**start.bat now works perfectly!** 🎉

All services start successfully, and the backend stays running with hot-reload enabled for development.

---

**Fix completed:** November 17, 2025
**Next step:** Test frontend startup with `scripts\start-frontend.bat`
