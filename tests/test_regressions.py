"""Regression safety net (mock-only — no AWS, no DB, no new infra).

The system interpreter intentionally has no web/AWS deps installed
(no flask, boto3, moto) and `app/db` shadows `poller/db` on sys.path,
so this module installs minimal stdlib stubs for `flask`,
`flask_httpauth`, `werkzeug.security` and `botocore.config`, then loads
the REAL production files (queries.py, rules.py, collectors,
routes/resources.py, app/main.py) by path. Every assertion executes
production code — only third-party imports are faked.

Covers the verified gap fixes:
  1. Upsert clock — tag-only upserts must not move last_modified; the IAM
     activity clock passes through; legacy DBs without migration 001 fall
     back to the old shape instead of raising.
  2. IAM rule SQL — measures last_activity_at with NULL-suppress semantics
     and make_interval(days => %s) params.
  3. SG ENI failure — fail-CLOSED (None sentinel + raise), never an empty
     set that marks every SG unused.
  4. Pagination clamp — page_size clamped to 1..500, bad input safe-parsed.
  5. Cost floors/placeholders — EIP floor, CloudFront placeholder, S3 zero,
     EKS first instance type.
  6. Version fallback — 'unknown' when VERSION is unreadable.
  7. SQL-fstring gate — no f-strings carrying SQL keywords in routes/rules.
  8. Env fallback — invalid thresholds fall back to safe defaults.
"""

import ast
import importlib.util
import os
import re
import sys
import types
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
POLLER_DIR = PROJECT_ROOT / "poller"
APP_DIR = PROJECT_ROOT / "app"
for _p in (str(PROJECT_ROOT), str(POLLER_DIR), str(APP_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Dependency-free loading helpers (stubs for missing third-party packages)
# ---------------------------------------------------------------------------


def _install_stub(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


def _identity_decorator(*dargs, **dkwargs):
    if dargs and callable(dargs[0]) and len(dargs) == 1 and not dkwargs:
        return dargs[0]

    def wrap(fn):
        return fn

    return wrap


class _StubBlueprint:
    def __init__(self, *args, **kwargs):
        self.routes = []

    def route(self, *args, **kwargs):
        def wrap(fn):
            self.routes.append(fn)
            return fn

        return wrap


class _StubFlaskApp:
    def __init__(self, *args, **kwargs):
        self.blueprints = []

    def context_processor(self, fn):
        return fn

    def teardown_appcontext(self, fn):
        return fn

    def before_request(self, fn):
        return fn

    def route(self, *args, **kwargs):
        return _identity_decorator

    def register_blueprint(self, bp):
        self.blueprints.append(bp)


class _StubHTTPBasicAuth:
    def __init__(self, *args, **kwargs):
        pass

    def verify_password(self, fn):
        return fn

    def login_required(self, fn=None, **kwargs):
        if fn is None:
            return _identity_decorator
        return fn


class _StubBotoConfig:
    def __init__(self, *args, **kwargs):
        pass


_FLASK_REQUEST = SimpleNamespace(args={}, path="/")

if "flask" not in sys.modules:
    try:
        import flask  # noqa: F401
    except ImportError:
        _install_stub(
            "flask",
            Flask=_StubFlaskApp,
            Blueprint=_StubBlueprint,
            jsonify=lambda obj, *a, **k: obj,
            render_template=lambda *a, **k: "",
            request=_FLASK_REQUEST,
            g=SimpleNamespace(),
        )

if "flask_httpauth" not in sys.modules:
    try:
        import flask_httpauth  # noqa: F401
    except ImportError:
        _install_stub("flask_httpauth", HTTPBasicAuth=_StubHTTPBasicAuth)

if "werkzeug.security" not in sys.modules:
    try:
        import werkzeug.security  # noqa: F401
    except ImportError:
        _install_stub("werkzeug", __path__=[])
        _install_stub(
            "werkzeug.security",
            generate_password_hash=lambda p: "stub:" + p,
            check_password_hash=lambda h, p: True,
        )

if "botocore.config" not in sys.modules:
    try:
        import botocore.config  # noqa: F401
    except ImportError:
        _install_stub("botocore", __path__=[])
        _install_stub("botocore.config", Config=_StubBotoConfig)


def _load_by_path(mod_name: str, path: Path) -> types.ModuleType:
    """Load a REAL production file under an alias module name."""
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _poller_queries():
    return _load_by_path("poller_db_queries_ut", POLLER_DIR / "db" / "queries.py")


def _route_resources():
    return _load_by_path("resources_route_ut", APP_DIR / "routes" / "resources.py")


def _app_main():
    return _load_by_path("app_main_ut", APP_DIR / "main.py")


# ---------------------------------------------------------------------------
# 1. Upsert clock (+ legacy fallback without migration 001)
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, fail_first_with=None):
        self.executes = []
        self.fail_first_with = fail_first_with
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.calls += 1
        if self.calls == 1 and self.fail_first_with is not None:
            raise self.fail_first_with
        self.executes.append((query, params))

    def fetchone(self):
        return (True,)


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, *args, **kwargs):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _norm_ws(text):
    return " ".join(text.split())


def _base_resource(**overrides):
    resource = {
        "resource_id": "i-123",
        "resource_type": "ec2",
        "resource_name": "web",
        "account_id": "123456789012",
        "region": "ap-south-1",
        "state": "running",
        "created_at": None,
        "tags": {"Owner": "team"},
        "estimated_cost_usd": Decimal("1.5"),
    }
    resource.update(overrides)
    return resource


def test_upsert_clock_state_change_only_and_activity_passthrough():
    queries = _poller_queries()

    cur = _FakeCursor()
    conn = _FakeConn(cur)
    result = queries.insert_or_update_resource(
        conn, _base_resource(last_activity_at=None)
    )
    assert result == "inserted"
    assert len(cur.executes) == 1
    query, params = cur.executes[0]
    flat = _norm_ws(query)
    # last_modified moves ONLY on state change — tag drift must not refresh it
    assert "IS DISTINCT FROM EXCLUDED.state" in flat
    assert "last_modified = NOW()" not in flat
    # Activity clock is written through verbatim (nullable)
    assert "last_activity_at" in flat
    assert params[7] is None

    # Non-null activity value passes through in the same position
    cur2 = _FakeCursor()
    conn2 = _FakeConn(cur2)
    queries.insert_or_update_resource(conn2, _base_resource(last_activity_at="2026-01-01"))
    assert cur2.executes[0][1][7] == "2026-01-01"

    # Legacy DB without migration 001: UndefinedColumn-style failure on the
    # new shape must roll back and retry the legacy shape — never raise.
    cur3 = _FakeCursor(
        fail_first_with=Exception('column "last_activity_at" does not exist')
    )
    conn3 = _FakeConn(cur3)
    result3 = queries.insert_or_update_resource(conn3, _base_resource())
    assert result3 == "inserted"
    assert conn3.rollbacks == 1
    assert len(cur3.executes) == 1
    assert "last_activity_at" not in _norm_ws(cur3.executes[0][0])

    # Unrelated DB errors must still propagate (no silent swallowing)
    cur4 = _FakeCursor(fail_first_with=Exception("connection reset by peer"))
    with pytest.raises(Exception, match="connection reset"):
        queries.insert_or_update_resource(_FakeConn(cur4), _base_resource())


# ---------------------------------------------------------------------------
# 2. IAM rule SQL
# ---------------------------------------------------------------------------


def test_iam_rule_uses_activity_clock_with_null_suppress():
    from alerts.rules import ALERT_RULES

    rule = next(r for r in ALERT_RULES if r["type"] == "iam_user_inactive")
    query = rule["query"]
    assert "last_activity_at" in query
    assert "last_modified" not in query
    assert "make_interval(days => %s)" in query
    assert "INTERVAL '%s" not in query
    assert "IS NOT NULL" in query
    params = rule["get_params"]()
    assert len(params) == 1 and isinstance(params[0], int)
    msg = rule["message_fn"]({"resource_name": "alice"})
    assert "alice" in msg


# ---------------------------------------------------------------------------
# 3. SG ENI failure is fail-CLOSED
# ---------------------------------------------------------------------------


class _RaisingENIPaginator:
    def paginate(self):
        raise RuntimeError("ENI outage")


class _FakeSGClient:
    def get_paginator(self, name):
        if name == "describe_network_interfaces":
            return _RaisingENIPaginator()
        raise AssertionError(f"unexpected paginator: {name}")


def test_sg_eni_failure_returns_none_and_collect_raises():
    from collectors.security_groups import SecurityGroupCollector

    collector = SecurityGroupCollector(None, "123456789012", "ap-south-1")
    # Sentinel: None on failure — never an empty set (fail-open bug)
    assert collector._get_in_use_sg_ids(_FakeSGClient()) is None

    # collect() must raise into the poller's partial_failure path
    collector._make_client = lambda service: _FakeSGClient()
    with pytest.raises(RuntimeError):
        collector.collect()


# ---------------------------------------------------------------------------
# 4. Pagination clamp (real route code, stubbed flask request)
# ---------------------------------------------------------------------------


class _FakeAPICursor:
    def __init__(self):
        self.executes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.executes.append((query, params))

    def fetchone(self):
        return {"total": 0}

    def fetchall(self):
        return []


class _FakeAPIConn:
    def __init__(self):
        self.cursor_obj = _FakeAPICursor()

    def cursor(self, *args, **kwargs):
        return self.cursor_obj


def _call_list_resources(monkeypatch, **qs):
    import flask

    route_mod = _route_resources()
    fake = _FakeAPIConn()
    monkeypatch.setattr(route_mod, "get_connection", lambda: fake)
    monkeypatch.setattr(flask.request, "args", dict(qs))
    payload = route_mod.list_resources()
    limit_param = fake.cursor_obj.executes[1][1][-2]
    return payload, limit_param


def test_pagination_clamp(monkeypatch):
    _, limit = _call_list_resources(monkeypatch, page_size="9999")
    assert limit == 500

    payload, limit = _call_list_resources(monkeypatch, page_size="0")
    assert payload["page_size"] == 1 and limit == 1

    payload, limit = _call_list_resources(monkeypatch, page_size="not-a-number")
    assert payload["page_size"] == 100 and limit == 100

    payload, _ = _call_list_resources(monkeypatch, page="0")
    assert payload["page"] == 1


# ---------------------------------------------------------------------------
# 5. Cost floors / placeholders / EKS first-type
# ---------------------------------------------------------------------------


def test_cost_floors_and_placeholders():
    from collectors.cloudfront import CloudFrontCollector
    from collectors.s3 import S3Collector
    from utils.cost import (
        estimate_eks_nodegroup_cost,
        estimate_elastic_ip_cost,
    )

    # EIP: 1-hour floor
    assert estimate_elastic_ip_cost() == Decimal("0.005")
    # CloudFront: daily placeholder
    assert CloudFrontCollector._DAILY_PLACEHOLDER_COST_USD == Decimal("0.01")
    # S3: zero (usage not metered in v1)
    assert S3Collector.RESOURCE_TYPE == "s3"

    # EKS: nodegroup cost uses the FIRST listed instance type only
    from datetime import datetime, timezone

    from collectors.eks import EKSCollector

    created = datetime(2026, 1, 1, tzinfo=timezone.utc)

    class _FakeEKS:
        def get_paginator(self, name):
            assert name == "list_nodegroups"

            class _P:
                def paginate(self, **kwargs):
                    yield {"nodegroups": ["ng-1"]}

            return _P()

        def describe_nodegroup(self, **kwargs):
            return {
                "nodegroup": {
                    "scalingConfig": {"desiredSize": 2, "minSize": 1, "maxSize": 3},
                    "instanceTypes": ["m5.large", "m5.xlarge"],
                    "createdAt": created,
                    "status": "ACTIVE",
                }
            }

    collector = EKSCollector(None, "123456789012", "ap-south-1")
    grouped = collector._collect_nodegroups(_FakeEKS(), "cluster", created)
    expected = estimate_eks_nodegroup_cost("m5.large", 2, created)
    assert grouped["cost"] == round(expected, 4)
    assert grouped["items"][0]["instance_types"] == ["m5.large", "m5.xlarge"]
    # ...and it must NOT equal the second-type pricing
    assert grouped["cost"] != round(
        estimate_eks_nodegroup_cost("m5.xlarge", 2, created), 4
    )


# ---------------------------------------------------------------------------
# 6. Version fallback
# ---------------------------------------------------------------------------


def test_version_fallback_unknown(monkeypatch):
    mod = _app_main()

    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setattr(os.path, "isfile", lambda path: False)
    assert mod._read_app_version() == "unknown"

    monkeypatch.setenv("APP_VERSION", "9.9.9-test")
    assert mod._read_app_version() == "9.9.9-test"


# ---------------------------------------------------------------------------
# 7. SQL-fstring gate (word-boundary match — avoids flagging words like
#    "deleted" while catching real SELECT/WHERE/FROM interpolation)
# ---------------------------------------------------------------------------


_SQL_WORD = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|WHERE|FROM)\b", re.IGNORECASE
)


def test_no_sql_fstrings_in_query_code():
    targets = [
        PROJECT_ROOT / "app" / "routes" / "resources.py",
        PROJECT_ROOT / "app" / "routes" / "alerts.py",
        PROJECT_ROOT / "app" / "routes" / "overview.py",
        PROJECT_ROOT / "app" / "routes" / "poller.py",
        PROJECT_ROOT / "poller" / "db" / "queries.py",
        PROJECT_ROOT / "poller" / "alerts" / "rules.py",
    ]
    violations = []
    for target in targets:
        if not target.exists():
            continue
        tree = ast.parse(target.read_text(), filename=str(target))
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                text = "".join(
                    str(v.value) if isinstance(v, ast.Constant) else "{...}"
                    for v in node.values
                )
                match = _SQL_WORD.search(text)
                if match:
                    violations.append(
                        f"{target}:{node.lineno} ({match.group(1).upper()})"
                    )
    assert violations == [], f"SQL in f-strings: {violations}"


# ---------------------------------------------------------------------------
# 8. Env fallback for thresholds
# ---------------------------------------------------------------------------


def test_env_threshold_fallbacks(monkeypatch):
    from alerts.rules import _days, _minutes

    monkeypatch.delenv("ALERT_EC2_RUNNING_DAYS", raising=False)
    assert _days("ALERT_EC2_RUNNING_DAYS", 30) == 30
    monkeypatch.setenv("ALERT_EC2_RUNNING_DAYS", "not-a-number")
    assert _days("ALERT_EC2_RUNNING_DAYS", 30) == 30
    monkeypatch.setenv("ALERT_EC2_RUNNING_DAYS", "45")
    assert _days("ALERT_EC2_RUNNING_DAYS", 30) == 45

    monkeypatch.setenv("ALERT_ECS_UNHEALTHY_MINS", "broken")
    assert _minutes("ALERT_ECS_UNHEALTHY_MINS", 10) == 10
