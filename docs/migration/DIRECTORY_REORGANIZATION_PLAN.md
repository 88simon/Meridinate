# Meridinate - Professional Directory Reorganization Plan

**Date:** November 17, 2025
**Status:** Recommendation / Not Yet Implemented
**Goal:** Achieve professional-grade directory organization

---

## Current Issues Identified

### **Critical Issues**

#### 1. **Nested `backend/backend/` Structure** ❌
```
C:\Meridinate\
└── backend\                    # Root
    └── backend\               # Nested (CONFUSING!)
        ├── app\               # FastAPI application
        ├── analyzed_tokens.db # Database
        └── ...
```
**Problem:** Double nesting is confusing and non-standard
**Impact:** Hard to navigate, unclear which "backend" is the project root

#### 2. **Mixed Concerns at Backend Root** ❌
```
backend/
├── action_wheel.ahk           # AutoHotkey (desktop automation)
├── action_wheel_settings.ini  # AHK config
├── analyzed_tokens.db         # Database file
├── docker_log.txt             # Log file
├── openapi_log.txt            # Log file
├── backend/                   # Python FastAPI app
├── Lib/                       # AutoHotkey library
├── tools/                     # AutoHotkey tools
└── userscripts/               # Browser extension
```
**Problem:** Python backend mixed with AutoHotkey scripts, logs, and database files
**Impact:** Unclear project boundaries, hard to containerize, poor separation of concerns

#### 3. **Database Files at Backend Code Level** ❌
```
backend/backend/
├── analyzed_tokens.db                      # Main database
├── analyzed_tokens_backup_20251110_*.db    # Backups (3 files)
└── analyzed_tokens_backup_before_restore.db
```
**Problem:** Database files mixed with source code
**Impact:** Risky for version control, poor data/code separation

#### 4. **Scattered Documentation** ❌
```
C:\Meridinate\
├── progress.md                # Top-level
├── CHECKLIST_ANALYSIS.md      # Top-level
├── MIGRATION_COMPLETE.md      # Top-level
└── backend/
    ├── README.md
    ├── SECURITY.md
    ├── OPSEC.md
    └── docs/
        ├── SECURITY_AUDIT.md
        └── SECURITY_QUICKFIX.md
```
**Problem:** Documentation scattered across multiple levels
**Impact:** Hard to find, maintain, and navigate

---

## Professional Standards Reference

### **Industry Standard: Python FastAPI Project**
```
project-name/
├── .github/              # GitHub-specific files
├── docs/                 # All documentation
├── src/                  # Source code (or app/)
│   └── app_name/
│       ├── api/          # API routes
│       ├── core/         # Core utilities
│       ├── models/       # Data models
│       ├── services/     # Business logic
│       └── main.py       # Entry point
├── tests/                # All tests
├── scripts/              # Utility scripts
├── data/                 # Data files (gitignored)
├── logs/                 # Log files (gitignored)
├── docker/               # Docker-related files
├── .env.example          # Environment template
├── pyproject.toml        # Python project config
├── Dockerfile
└── README.md
```

### **Industry Standard: Next.js Frontend**
```
frontend/
├── .github/
├── public/              # Static assets
├── src/
│   ├── app/            # Next.js 13+ App Router
│   ├── components/     # React components
│   ├── lib/            # Utilities
│   ├── hooks/          # Custom hooks
│   ├── types/          # TypeScript types
│   └── config/         # Configuration
├── tests/              # E2E and unit tests
├── .env.local.example
├── package.json
└── README.md
```

### **Industry Standard: Monorepo**
```
project/
├── apps/                    # Applications
│   ├── backend/            # FastAPI backend
│   └── frontend/           # Next.js frontend
├── packages/                # Shared packages
│   ├── types/              # Shared TypeScript types
│   └── config/             # Shared configs
├── tools/                   # Development tools
├── scripts/                 # Build/deployment scripts
├── docs/                    # Unified documentation
└── README.md
```

---

## Recommended Reorganization

### **Option 1: Monorepo (Recommended for Your Case)**

```
C:\Meridinate\                           # Project root
├── .github/                             # Unified CI/CD workflows
│   └── workflows/
│       ├── backend-ci.yml              # Backend checks
│       ├── frontend-ci.yml             # Frontend checks
│       └── sync-types.yml              # Type synchronization
│
├── docs/                                # All project documentation
│   ├── README.md                       # Main project docs
│   ├── SECURITY.md                     # Security policy
│   ├── OPSEC.md                        # Operational security
│   ├── migration/                      # Migration docs (historical)
│   │   ├── MIGRATION_COMPLETE.md
│   │   └── CLEANUP_SUMMARY.md
│   ├── progress/                       # Development logs
│   │   ├── progress.md
│   │   └── CHECKLIST_ANALYSIS.md
│   └── architecture/                   # Architecture docs
│       └── api-types-sync.md
│
├── apps/                                # Application code
│   │
│   ├── backend/                        # FastAPI backend
│   │   ├── src/                        # Source code
│   │   │   └── meridinate/             # Package name
│   │   │       ├── api/                # API routes (routers)
│   │   │       ├── core/               # Core utilities
│   │   │       ├── models/             # Pydantic models
│   │   │       ├── services/           # Business logic
│   │   │       ├── database/           # Database logic
│   │   │       ├── observability/      # Logging/monitoring
│   │   │       └── main.py             # FastAPI app entry
│   │   ├── tests/                      # Backend tests
│   │   ├── scripts/                    # Python utility scripts
│   │   │   └── backup_db.py
│   │   ├── data/                       # Data files (gitignored)
│   │   │   ├── db/                     # Database files
│   │   │   ├── backups/                # Database backups
│   │   │   ├── analysis_results/       # Analysis output
│   │   │   └── axiom_exports/          # Axiom exports
│   │   ├── logs/                       # Log files (gitignored)
│   │   ├── docker/                     # Docker configs
│   │   │   ├── Dockerfile
│   │   │   └── docker-compose.yml
│   │   ├── .env.example                # Environment template
│   │   ├── pyproject.toml              # Python deps/config
│   │   ├── requirements.txt            # Production deps
│   │   ├── requirements-dev.txt        # Dev deps
│   │   └── README.md
│   │
│   └── frontend/                       # Next.js frontend (KEEP AS IS ✓)
│       ├── src/
│       ├── public/
│       ├── tests/
│       ├── package.json
│       └── README.md
│
├── tools/                              # Development tools
│   │
│   ├── autohotkey/                    # AutoHotkey scripts
│   │   ├── action_wheel.ahk
│   │   ├── action_wheel_settings.ini
│   │   ├── lib/                       # AHK libraries
│   │   │   └── Gdip_All.ahk
│   │   └── tools/                     # AHK utilities
│   │       └── test_mouse_buttons.ahk
│   │
│   └── browser/                        # Browser extensions
│       └── userscripts/
│           └── defined-fi-autosearch.user.js
│
├── scripts/                            # Build/deployment scripts
│   ├── start.sh                        # Start all services
│   ├── start-backend.sh
│   ├── start-frontend.sh
│   ├── run-ci-checks.sh                # CI validation
│   └── docker-test.sh
│
├── .gitignore                          # Unified gitignore
├── README.md                           # Main project README
└── LICENSE
```

**Benefits:**
- ✅ Clear separation of concerns
- ✅ Scalable structure (can add more apps)
- ✅ Professional/enterprise-grade
- ✅ Easy to understand for new developers
- ✅ Better CI/CD organization
- ✅ Clean Docker context

---

### **Option 2: Simplified Cleanup (Minimal Changes)**

Keep current structure but fix critical issues:

```
C:\Meridinate\
├── backend/                            # Keep current name
│   ├── ahk/                           # NEW: Move AutoHotkey here
│   │   ├── action_wheel.ahk
│   │   ├── action_wheel_settings.ini
│   │   ├── lib/
│   │   └── tools/
│   ├── src/                            # NEW: Rename backend/ to src/
│   │   └── app/                       # FastAPI app (from backend/backend/app/)
│   ├── data/                           # NEW: Data files (gitignored)
│   │   ├── analyzed_tokens.db
│   │   ├── backups/
│   │   ├── analysis_results/
│   │   └── axiom_exports/
│   ├── logs/                           # NEW: Log files
│   │   ├── docker_log.txt
│   │   └── openapi_log.txt
│   ├── tests/
│   ├── docs/                           # Keep
│   ├── scripts/                        # NEW: Move Python scripts here
│   ├── start.bat
│   └── README.md
│
├── frontend/                           # Keep as is ✓
│
└── docs/                               # NEW: Top-level docs
    ├── migration/
    ├── progress/
    └── README.md
```

**Benefits:**
- ✅ Less disruptive
- ✅ Fixes nested backend/backend/ issue
- ✅ Separates data from code
- ✅ Clearer organization
- ⚠️ Still mixes AutoHotkey with Python

---

## Specific Improvements Recommended

### **1. Flatten Nested Structure** (Critical)
**Current:**
```
backend/backend/app/
```
**Should be:**
```
backend/src/app/  or  apps/backend/src/
```

### **2. Separate Data from Code** (Critical)
**Current:**
```
backend/backend/analyzed_tokens.db
backend/backend/analyzed_tokens_backup_*.db
```
**Should be:**
```
backend/data/db/analyzed_tokens.db
backend/data/backups/*.db
```

### **3. Centralize Logs** (Important)
**Current:**
```
backend/docker_log.txt
backend/openapi_log.txt
```
**Should be:**
```
backend/logs/docker.log
backend/logs/openapi.log
```
**Add to .gitignore:**
```
logs/
*.log
```

### **4. Separate AutoHotkey from Python** (Important)
**Current:**
```
backend/
├── action_wheel.ahk
├── Lib/Gdip_All.ahk
├── tools/test_mouse_buttons.ahk
└── backend/app/  # Python
```
**Should be:**
```
tools/autohotkey/
├── action_wheel.ahk
├── lib/Gdip_All.ahk
└── tools/test_mouse_buttons.ahk

apps/backend/src/  # Python only
```

### **5. Organize Documentation** (Nice to have)
**Current:**
```
C:\Meridinate\progress.md
C:\Meridinate\CHECKLIST_ANALYSIS.md
backend/docs/SECURITY_AUDIT.md
```
**Should be:**
```
docs/
├── README.md
├── SECURITY.md
├── progress/
│   ├── 2025-11-17-bug-fixes.md
│   └── checklist-analysis.md
├── migration/
│   └── 2025-11-17-meridinate-migration.md
└── architecture/
```

### **6. Use `pyproject.toml`** (Modern Python)
**Add:**
```toml
[project]
name = "meridinate"
version = "2.0.0"
description = "Solana token analysis toolkit"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]

[tool.black]
line-length = 100

[tool.isort]
profile = "black"
```

---

## Migration Steps (If Choosing Option 1)

### **Phase 1: Backend Restructure** (1-2 hours)
1. Create new directory structure
2. Move `backend/backend/app/` → `apps/backend/src/meridinate/`
3. Move database files → `apps/backend/data/`
4. Move tests → `apps/backend/tests/`
5. Update imports in Python files
6. Update `Dockerfile` and `docker-compose.yml`
7. Test backend startup

### **Phase 2: Separate AutoHotkey** (30 mins)
1. Create `tools/autohotkey/`
2. Move `action_wheel.ahk`, `Lib/`, `tools/` → `tools/autohotkey/`
3. Update `start.bat` paths
4. Test AutoHotkey functionality

### **Phase 3: Documentation** (30 mins)
1. Create `docs/` structure
2. Move markdown files to appropriate subdirectories
3. Update cross-references
4. Create main `docs/README.md`

### **Phase 4: CI/CD Updates** (30 mins)
1. Move workflows to root `.github/`
2. Update paths in workflow files
3. Test CI/CD pipelines

---

## Professional Examples for Reference

### **FastAPI Projects**
- ✅ [Full Stack FastAPI Template](https://github.com/tiangolo/full-stack-fastapi-template) - Official FastAPI template
- ✅ [FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices)

### **Next.js Projects**
- ✅ [Next.js Commerce](https://github.com/vercel/commerce) - Vercel's official example
- ✅ [T3 Stack](https://create.t3.gg/) - Type-safe Next.js starter

### **Monorepo Examples**
- ✅ [Turborepo](https://turbo.build/repo) - Modern monorepo tool
- ✅ [Nx Monorepo](https://nx.dev/) - Enterprise monorepo framework

---

## Comparison: Current vs Professional

| Aspect | Current | Professional | Impact |
|--------|---------|--------------|--------|
| **Nesting** | `backend/backend/app/` | `apps/backend/src/` or `src/app/` | High |
| **Data/Code Mix** | Database in code folder | `data/` folder (gitignored) | High |
| **Concerns Separation** | Mixed AHK + Python | Separate `tools/` and `apps/` | High |
| **Log Management** | Logs at root | `logs/` folder (gitignored) | Medium |
| **Documentation** | Scattered | Centralized `docs/` | Medium |
| **Docker Context** | Mixed files | Clean `apps/backend/` context | Medium |
| **Python Config** | `requirements.txt` only | `pyproject.toml` (modern) | Low |

---

## Recommendation

**Start with Option 2 (Simplified Cleanup)** to fix critical issues with minimal disruption:
1. ✅ Flatten `backend/backend/` → `backend/src/`
2. ✅ Separate data → `backend/data/`
3. ✅ Move logs → `backend/logs/`
4. ✅ Move AutoHotkey → `backend/ahk/` (or `tools/autohotkey/`)

**Later migrate to Option 1 (Monorepo)** when ready for:
- Multiple backend services
- Shared packages between backend/frontend
- Enterprise-grade organization

---

**Next Steps:**
1. Review this plan
2. Choose Option 1 or Option 2
3. I'll execute the reorganization
4. Update documentation and CI/CD
5. Test all services

**Estimated Time:**
- Option 1: 2-3 hours
- Option 2: 1 hour

Would you like me to proceed with either option?
