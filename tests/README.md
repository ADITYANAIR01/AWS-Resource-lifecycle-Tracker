# AWS Resource Lifecycle Tracker — Security Tests

Automated security tests to prevent SQL injection and validate query behavior.

---

## Test Files

```
tests/
└── conftest.py                           # pytest fixtures (for future tests)

app/routes/
├── test_sql_security.py                  # ✅ AST-based SQL injection detector
└── test_query_behavior.py                # ✅ Query logic validator
```

---

## Running Tests

### Security Tests (Quick Check)
```bash
./run_tests.sh security
```

### Individual Tests
```bash
# SQL injection check
python3 app/routes/test_sql_security.py

# Query behavior validation
python3 app/routes/test_query_behavior.py
```

---

## What These Tests Do

### 1. SQL Security Test (`test_sql_security.py`)
- **Purpose:** Detect SQL injection vulnerabilities
- **Method:** AST parser scans for f-strings containing SQL keywords
- **Coverage:** All Flask routes in `app/routes/`
- **Runtime:** <1 second
- **Pass Criteria:** Zero f-strings with SQL keywords (SELECT, INSERT, UPDATE, DELETE, WHERE)

### 2. Query Behavior Test (`test_query_behavior.py`)
- **Purpose:** Validate NULL-check pattern produces correct SQL logic
- **Method:** Simulates all filter combinations and verifies WHERE clause equivalence
- **Coverage:** Alerts and Resources API endpoints
- **Runtime:** <1 second
- **Pass Criteria:** All filter combinations match expected SQL logic

---

## Adding More Tests (Future)

When ready to add unit/integration tests:

1. Install test dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

2. Create test files in `tests/`:
   ```
   tests/
   ├── test_collectors.py  # Unit tests for resource collectors
   ├── test_cost.py        # Unit tests for cost estimation
   └── test_routes.py      # Integration tests for Flask APIs
   ```

3. Run with pytest:
   ```bash
   pytest tests/ -v
   ```
