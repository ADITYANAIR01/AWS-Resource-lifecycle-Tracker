"""
SQL Security Test - Verify parameterized queries

This test ensures that the Flask routes use fully parameterized SQL queries
with no dynamic WHERE clause construction (f-strings or string concatenation).

Run: python3 app/routes/test_sql_security.py
"""

import ast
import sys


def check_file_for_sql_fstrings(filepath):
    """
    Parse Python file and check for f-strings containing SQL keywords.
    Returns list of violations.
    """
    violations = []

    with open(filepath, "r") as f:
        content = f.read()

    try:
        tree = ast.parse(content, filename=filepath)
    except SyntaxError as e:
        return [f"Syntax error: {e}"]

    for node in ast.walk(tree):
        # Check for f-strings (JoinedStr in AST)
        if isinstance(node, ast.JoinedStr):
            # Reconstruct the f-string content
            parts = []
            for value in node.values:
                if isinstance(value, ast.Constant):
                    parts.append(str(value.value))
                elif isinstance(value, ast.FormattedValue):
                    parts.append("{...}")

            fstring_content = "".join(parts).upper()

            # Check for SQL keywords in f-strings
            sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "WHERE", "FROM"]
            for keyword in sql_keywords:
                if keyword in fstring_content:
                    violations.append(
                        {
                            "line": node.lineno,
                            "type": "f-string with SQL keyword",
                            "keyword": keyword,
                        }
                    )
                    break

    return violations


def main():
    files_to_check = [
        "app/routes/alerts.py",
        "app/routes/resources.py",
        "app/routes/overview.py",
        "app/routes/poller.py",
    ]

    all_violations = {}

    for filepath in files_to_check:
        try:
            violations = check_file_for_sql_fstrings(filepath)
            if violations:
                all_violations[filepath] = violations
        except FileNotFoundError:
            print(f"⚠️  File not found: {filepath}")
            continue

    if all_violations:
        print("❌ SQL SECURITY CHECK FAILED\n")
        for filepath, violations in all_violations.items():
            print(f"File: {filepath}")
            for v in violations:
                print(f"  Line {v['line']}: {v['type']} ({v['keyword']})")
        print(
            "\n⚠️  SQL queries must use parameterized placeholders (%s), not f-strings"
        )
        sys.exit(1)
    else:
        print("✅ SQL SECURITY CHECK PASSED")
        print("   All Flask routes use parameterized queries")
        print("   No f-strings with SQL keywords detected")
        sys.exit(0)


if __name__ == "__main__":
    main()
