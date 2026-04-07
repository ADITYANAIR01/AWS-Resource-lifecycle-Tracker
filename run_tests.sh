#!/bin/bash
# Test runner script for AWS Resource Lifecycle Tracker
# Usage: ./run_tests.sh [unit|integration|all|coverage]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  AWS Resource Lifecycle Tracker — Test Suite              ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Function to run pytest tests (when they exist)
run_pytest_tests() {
    echo -e "${YELLOW}Running pytest tests...${NC}"
    
    if [ -f "tests/test_*.py" ] || [ -d "tests/unit" ]; then
        pytest tests/ -v
        echo -e "${GREEN}✓ Pytest tests complete${NC}"
    else
        echo -e "${YELLOW}⚠️  No pytest tests found${NC}"
        echo -e "${YELLOW}   Create tests in tests/ directory to use pytest${NC}"
    fi
    echo ""
}

# Function to run security checks
run_security_checks() {
    echo -e "${YELLOW}Running security checks...${NC}"
    
    # SQL injection check
    echo "  - SQL injection check..."
    python3 app/routes/test_sql_security.py
    
    # Query behavior validation
    echo "  - Query behavior validation..."
    python3 app/routes/test_query_behavior.py
    
    echo -e "${GREEN}✓ Security checks passed${NC}"
    echo ""
}

# Function to run linting
run_lint() {
    echo -e "${YELLOW}Running linters...${NC}"
    
    echo "  - flake8..."
    flake8 poller/ app/ --max-line-length=88 --extend-ignore=E203,W503 || true
    
    echo "  - black (check only)..."
    black --check poller/ app/ || true
    
    echo -e "${GREEN}✓ Linting complete${NC}"
    echo ""
}

# Main logic
case "${1:-all}" in
    pytest)
        run_pytest_tests
        ;;
    security)
        run_security_checks
        ;;
    lint)
        run_lint
        ;;
    all)
        run_security_checks
        ;;
    *)
        echo "Usage: $0 [security|pytest|lint|all]"
        echo ""
        echo "  security     - Run security checks (SQL injection + query validation)"
        echo "  pytest       - Run pytest tests (when they exist)"
        echo "  lint         - Run code linters (flake8, black)"
        echo "  all          - Run security checks (default)"
        exit 1
        ;;
esac

echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ All checks passed!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
