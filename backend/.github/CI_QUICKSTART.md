# CI Quick Start Guide

Fast reference for Meridinate's backend CI/CD pipeline.

> **Note:** The frontend (gun-del-sol-web) has its own CI pipeline in its separate repository.

## Quick Commands

### Run All Checks Locally
```bash
# Windows
run_ci_checks.bat

# Unix/Linux/macOS
chmod +x run_ci_checks.sh
./run_ci_checks.sh
```

### Fix Common Issues

**Backend formatting:**
```bash
cd backend
black .
isort .
```

**Run tests:**
```bash
cd backend
pytest -v
```

**Check linting:**
```bash
cd backend
flake8 .
```

## Workflow Status

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| **CI** | Every push/PR | Main pipeline (backend checks) |
| **Backend CI** | Changes to `backend/**` | Backend-specific checks |
| **OpenAPI Schema** | Changes to `backend/app/**` | Export API schema and types |

## Pre-Push Checklist

- [ ] Run `run_ci_checks.bat` (or `.sh`)
- [ ] All backend tests pass
- [ ] No linting errors (Black, isort, flake8)
- [ ] No TypeScript type errors in generated types
- [ ] Commit messages follow conventions

## Setup Requirements

**Backend (Production):**
```bash
cd backend
pip install -r requirements.txt
```

**Backend (Development - includes testing tools):**
```bash
cd backend
pip install -r requirements-dev.txt
```

## Common Issues

### "Black found formatting issues"
```bash
cd backend && black .
```

### "isort found issues"
```bash
cd backend && isort .
```

### "flake8 linting errors"
```bash
cd backend && flake8 .
# Check output for specific issues
```

### "Tests failing"
```bash
# Check test isolation
cd backend && pytest -v --lf  # Run last failed

# Full test output
pytest -v -s

# Check coverage
pytest --cov=app --cov-report=term
```

### "Dependencies not installing"
```bash
# Make sure you're using the dev requirements
pip install -r requirements-dev.txt

# Clear cache if needed
pip cache purge
pip install -r requirements-dev.txt
```

## GitHub Secrets

Add to repository settings: Settings → Secrets and variables → Actions:

| Secret | Required | Purpose |
|--------|----------|---------|
| `CODECOV_TOKEN` | No | Coverage reports |
| `GITHUB_TOKEN` | Auto | PR creation (auto-provided) |

## Status Badges

Add to README.md (replace YOUR_USERNAME/YOUR_REPO):
```markdown
![CI](https://github.com/YOUR_USERNAME/YOUR_REPO/workflows/CI/badge.svg)
![Backend CI](https://github.com/YOUR_USERNAME/YOUR_REPO/workflows/Backend%20CI/badge.svg)
```

## Configuration Files

| File | Purpose |
|------|---------|
| `backend/.flake8` | Flake8 linter config |
| `backend/pyproject.toml` | Black, isort, pytest config |
| `backend/pytest.ini` | Pytest settings |
| `backend/requirements.txt` | Production dependencies |
| `backend/requirements-dev.txt` | Development and testing dependencies |

## CI Pipeline Flow

```
Push/PR to main/develop
         |
    [CI Workflow]
         |
    +----+----+
    |         |
  Lint      Test
    |         |
    +----+----+
         |
   All Checks
```

## Pro Tips

1. **Fast feedback:** Run `run_ci_checks.bat` before committing
2. **Auto-fix:** Use `black .` and `isort .` to auto-fix most issues
3. **Parallel checks:** Lint and test run in parallel on GitHub
4. **Cache:** Dependencies are cached - first run is slow, subsequent runs are fast
5. **Local config:** Test configs are auto-created in CI, but you may need them locally

## Dependencies

**Production (`requirements.txt`):**
- Core FastAPI and Solana libraries only
- Used by `start_backend.bat` and production deployments

**Development (`requirements-dev.txt`):**
- Includes all production dependencies
- Plus: pytest, black, flake8, isort, coverage tools
- Used by CI workflows and local development

## More Info

- [Full CI Documentation](.github/workflows/README.md)
- [Backend Testing Guide](../backend/tests/README.md)
- [CI Fixes Applied](CI_FIXES_APPLIED.md)
- [GitHub Actions Docs](https://docs.github.com/actions)

---

**Need help?** Check `.github/workflows/README.md` for detailed documentation.
