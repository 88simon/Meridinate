# Gun Del Sol Test Suite

Comprehensive test suite for the modular FastAPI backend.

## Overview

The test suite covers:
- ✅ All router endpoints (watchlist, tokens, wallets, tags, settings)
- ✅ Service layer (watchlist service)
- ✅ Utility functions (validators)
- ✅ Integration tests with test database
- ✅ Unit tests for business logic

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── routers/                 # Router endpoint tests
│   ├── test_settings_debug.py
│   ├── test_watchlist.py
│   ├── test_tokens.py
│   ├── test_wallets.py
│   └── test_tags.py
├── services/                # Service layer tests
│   └── test_watchlist_service.py
└── utils/                   # Utility function tests
    └── test_validators.py
```

## Running Tests

### Install Test Dependencies

```bash
cd backend
pip install pytest pytest-asyncio pytest-mock
```

### Run All Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=app --cov-report=html
```

### Run Specific Tests

```bash
# Run tests for a specific module
pytest tests/routers/test_watchlist.py

# Run tests for a specific class
pytest tests/routers/test_watchlist.py::TestAddressRegistration

# Run a specific test
pytest tests/routers/test_watchlist.py::TestAddressRegistration::test_register_valid_address

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration
```

### Run Tests with Output

```bash
# Show print statements
pytest -s

# Show detailed output
pytest -vv

# Show test coverage
pytest --cov=app
```

## Test Markers

Tests are marked with the following markers:
- `@pytest.mark.unit` - Fast unit tests, no database
- `@pytest.mark.integration` - Integration tests with database
- `@pytest.mark.slow` - Slow tests (mocked external API calls)

## Fixtures

Common fixtures available in all tests (from `conftest.py`):

- `test_client` - FastAPI TestClient with test database
- `test_db` - Temporary test database (function scope)
- `sample_token_data` - Sample token data for testing
- `sample_wallet_address` - Valid Solana address for testing
- `sample_early_bidders` - Sample wallet data
- `sample_analysis_settings` - Sample API settings

## Writing New Tests

### Example Test

```python
import pytest
from fastapi.testclient import TestClient

@pytest.mark.unit
class TestNewFeature:
    def test_my_endpoint(self, test_client: TestClient):
        """Test description"""
        response = test_client.get("/my-endpoint")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
```

### Best Practices

1. **Use descriptive test names** - Name tests `test_what_should_happen`
2. **One assertion concept per test** - Test one thing at a time
3. **Use fixtures** - Reuse common setup with fixtures
4. **Mark tests appropriately** - Use `@pytest.mark.unit` or `@pytest.mark.integration`
5. **Test edge cases** - Invalid inputs, empty data, etc.
6. **Clean up** - Use fixtures that auto-cleanup temporary data

## Test Coverage

Current test coverage:

- **Routers**: ~90% coverage
  - Settings/Debug: ✅ Full coverage
  - Watchlist: ✅ Full coverage
  - Tokens: ✅ CRUD, trash, history
  - Wallets: ✅ Multi-token queries, balance refresh
  - Tags: ✅ CRUD tags, Codex

- **Services**: ~85% coverage
  - Watchlist Service: ✅ Full coverage

- **Utils**: ~95% coverage
  - Validators: ✅ Full coverage

## Continuous Integration

To integrate with CI/CD:

```yaml
# .github/workflows/test.yml (example)
name: Test Suite
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.8'
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-asyncio pytest-mock pytest-cov
      - run: pytest --cov=app --cov-report=xml
      - uses: codecov/codecov-action@v2
```

## Troubleshooting

### Tests fail with database errors

Make sure the test database path is writable:
```bash
# Check permissions
ls -la backend/tests/
```

### Import errors

Make sure you're running from the backend directory:
```bash
cd backend
pytest
```

### Fixtures not found

Check that `conftest.py` is in the tests directory and properly formatted.

## Adding New Tests

When adding new features:

1. Write tests first (TDD approach)
2. Create fixtures for common test data
3. Add integration tests for endpoints
4. Add unit tests for business logic
5. Run full test suite before committing

## Test Report

Generate HTML test report:

```bash
pytest --html=test-report.html --self-contained-html
```

View the report by opening `test-report.html` in your browser.