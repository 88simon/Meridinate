# Gun Del Sol CI/CD Workflows

This directory contains GitHub Actions workflows for continuous integration of the Gun Del Sol backend.

> **Note:** The frontend (gun-del-sol-web) is maintained in a separate repository with its own CI pipeline.

## Workflows Overview

### 1. CI (Main Pipeline) - `ci.yml`
**Trigger:** Every push and PR to `main`/`develop` branches

Comprehensive backend pipeline that runs:
- Backend linting (Black, isort, flake8)
- Backend tests (pytest with coverage)
- All checks gate (ensures all jobs pass)

**Status Badge:**
```markdown
![CI](https://github.com/YOUR_USERNAME/YOUR_REPO/workflows/CI/badge.svg)
```

### 2. Backend CI - `backend-ci.yml`
**Trigger:** Changes to `backend/**` files

Specialized backend pipeline with:
- **Lint Job:** Code formatting (Black, isort) and linting (flake8)
- **Test Job:** Full test suite with coverage reports
- **Matrix Test Job:** Tests across Python 3.10, 3.11, and 3.12

**Features:**
- Uploads coverage to Codecov (requires `CODECOV_TOKEN` secret)
- Caches pip dependencies for faster runs
- Creates test config files automatically

### 3. OpenAPI Schema Export - `openapi-schema.yml`
**Trigger:** Changes to `backend/app/**` or manual dispatch

Automated API documentation pipeline:
- Exports FastAPI OpenAPI schema
- Validates schema structure
- Generates TypeScript types (on main branch only)
- Creates PR with updated types automatically

**Features:**
- Comments on PRs with endpoint counts
- Stores schema as artifact (90 days retention)
- Auto-generates TypeScript types for frontend integration

## Getting Started

### Prerequisites

**Backend:**
```bash
cd backend

# Production dependencies
pip install -r requirements.txt

# Development dependencies (includes testing and linting tools)
pip install -r requirements-dev.txt
```

### Running Checks Locally

**Backend:**
```bash
cd backend

# Formatting
black --check .
isort --check .

# Linting
flake8 .

# Tests
pytest --cov=app -v
```

**Quick validation (all checks):**
```bash
# Windows
run_ci_checks.bat

# Unix/Linux/macOS
./run_ci_checks.sh
```

## Configuration Files

### Backend Linting
- [`.flake8`](../../backend/.flake8) - Flake8 configuration
- [`pyproject.toml`](../../backend/pyproject.toml) - Black, isort, pytest config
- [`pytest.ini`](../../backend/pytest.ini) - Pytest settings

## Required Secrets

Add these secrets to your GitHub repository settings (Settings → Secrets → Actions):

| Secret | Purpose | Required |
|--------|---------|----------|
| `CODECOV_TOKEN` | Upload coverage reports to Codecov | Optional |
| `GITHUB_TOKEN` | Auto-create PRs with generated types | Auto-provided |

## Status Badges

Add these to your README.md (replace YOUR_USERNAME/YOUR_REPO):

```markdown
![CI](https://github.com/YOUR_USERNAME/YOUR_REPO/workflows/CI/badge.svg)
![Backend CI](https://github.com/YOUR_USERNAME/YOUR_REPO/workflows/Backend%20CI/badge.svg)
```

## Best Practices

1. **Before Pushing:**
   - Run linting and tests locally
   - Use `run_ci_checks.bat` or `run_ci_checks.sh` to validate
   - Fix issues with `black .` and `isort .`

2. **PR Guidelines:**
   - Ensure all checks pass before requesting review
   - Address any linting or test failures
   - Review OpenAPI schema changes in PR comments

3. **Performance Tips:**
   - Workflows use caching for dependencies (pip)
   - Backend tests create fresh config files each run
   - First run is slower, subsequent runs are fast

## Troubleshooting

### Backend Tests Failing
- Check that all test fixtures are properly isolated
- Ensure config files are created (workflows handle this automatically)
- Verify SQLite database migrations are up to date
- Run `pytest -v --lf` to see last failed tests

### Backend Linting Failing
- Run `black .` to auto-format
- Run `isort .` to fix import ordering
- Check flake8 output for specific issues

### Workflow Not Triggering
- Check path filters in workflow files
- Ensure you're pushing to `main` or `develop` branch
- Verify `.github/workflows/` is in root directory
- Check GitHub Actions tab for disabled workflows

### Dependencies Not Installing
- Verify `requirements-dev.txt` exists and is valid
- Check for conflicting package versions
- Clear pip cache: `pip cache purge`

## Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [FastAPI OpenAPI Schema](https://fastapi.tiangolo.com/advanced/extending-openapi/)
- [pytest Best Practices](https://docs.pytest.org/en/stable/goodpractices.html)
- [Black Code Style](https://black.readthedocs.io/)
- [isort Documentation](https://pycqa.github.io/isort/)

## Workflow Details

### CI Workflow (`ci.yml`)
- Runs on every push/PR to main/develop
- Two parallel jobs: lint and test
- Final gate job ensures both pass
- Uses `requirements-dev.txt` for dependencies

### Backend CI Workflow (`backend-ci.yml`)
- Triggered only when `backend/**` files change
- Three jobs: lint, test, and matrix test
- Matrix test runs on Python 3.10, 3.11, 3.12
- Uploads coverage to Codecov if token is set

### OpenAPI Schema Workflow (`openapi-schema.yml`)
- Triggered when `backend/app/**` changes or manually
- Exports OpenAPI schema from FastAPI app
- Validates schema is valid JSON
- On main branch: generates TypeScript types
- Creates PR with updated types (if needed)
- Comments on PRs with endpoint information

## Future Enhancements

Planned improvements:
- [ ] Add E2E testing with Playwright
- [ ] Implement Docker build and push
- [ ] Add deployment workflows (staging/production)
- [ ] Set up automated dependency updates (Dependabot)
- [ ] Add security scanning (CodeQL, Snyk)
- [ ] Performance benchmarking for API endpoints
- [ ] Automated changelog generation
