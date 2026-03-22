"""
Static snapshot generator.

Queries RDS for current dashboard state and generates
self-contained HTML files — one per dashboard page.

Each HTML file:
  - Has all CSS and JS inlined (no external dependencies)
  - Has all data embedded as window.__SNAPSHOT_DATA__
  - Shows a snapshot banner at the top
  - Looks identical to the live dashboard

The JS files detect window.__SNAPSHOT_DATA__ and serve
data from it instead of calling the Flask API.
"""

import json
import os
from datetime import datetime, timezone
from decimal import Decimal

from psycopg2.extras import RealDictCursor

from utils.logger import get_logger

logger = get_logger("poller.export.generator")

# Paths to static assets — mounted from app container via docker-compose volume
_STATIC_DIR = os.environ.get("STATIC_DIR", "/home/appuser/static")
_CSS_PATH    = os.path.join(_STATIC_DIR, "css", "dashboard.css")
_JS_DIR      = os.path.join(_STATIC_DIR, "js")


# ---------------------------------------------------------------------------
# JSON serializer — handles datetime, Decimal
# ---------------------------------------------------------------------------

class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _to_json(obj) -> str:
    return json.dumps(obj, cls=_Encoder)


# ---------------------------------------------------------------------------
# Asset loading
# ---------------------------------------------------------------------------

def _read_file(path: str, fallback: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.warning(f"Could not read {path}: {e}")
        return fallback


def _load_css() -> str:
    return _read_file(_CSS_PATH)


def _load_js(filename: str) -> str:
    return _read_file(os.path.join(_JS_DIR, filename))


# ---------------------------------------------------------------------------
# Data queries — same data that Flask API endpoints return
# ---------------------------------------------------------------------------

def _query_overview(conn) -> dict:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT resource_type, COUNT(*) as count
            FROM resources WHERE is_active = TRUE
            GROUP BY resource_type ORDER BY count DESC
        """)
        resources_by_type = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT severity, COUNT(*) as count FROM alerts
            WHERE resolved_at IS NULL GROUP BY severity
        """)
        alerts_by_severity = {r["severity"]: r["count"] for r in cur.fetchall()}

        cur.execute("""
            SELECT COALESCE(SUM(estimated_cost_usd), 0) as total
            FROM resources WHERE is_active = TRUE
        """)
        total_cost = float(cur.fetchone()["total"])

        cur.execute("""
            SELECT id, status, started_at, completed_at,
                   resources_found, alerts_triggered, error_log
            FROM poller_runs ORDER BY started_at DESC LIMIT 1
        """)
        row = cur.fetchone()
        last_run = dict(row) if row else None

    return {
        "total_resources":    sum(r["count"] for r in resources_by_type),
        "resources_by_type":  resources_by_type,
        "total_alerts":       sum(alerts_by_severity.values()),
        "alerts_by_severity": alerts_by_severity,
        "total_cost_usd":     round(total_cost, 2),
        "last_run":           last_run,
    }


def _query_resources(conn) -> dict:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT resource_id, resource_type, resource_name,
                   account_id, region, state, created_at, first_seen,
                   last_seen, last_modified, tags, estimated_cost_usd,
                   is_active, deleted_at
            FROM resources WHERE is_active = TRUE
            ORDER BY first_seen DESC
            LIMIT 500
        """)
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            if d.get("estimated_cost_usd"):
                d["estimated_cost_usd"] = float(d["estimated_cost_usd"])
            rows.append(d)
    return {"resources": rows, "total": len(rows), "page": 1, "page_size": 500, "pages": 1}


def _query_alerts(conn) -> dict:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT a.id, a.resource_id, a.resource_type,
                   a.alert_type, a.severity, a.message,
                   a.triggered_at, a.resolved_at, a.acknowledged,
                   r.resource_name, r.region
            FROM alerts a
            LEFT JOIN resources r
                ON  a.resource_id   = r.resource_id
                AND a.resource_type = r.resource_type
            ORDER BY a.triggered_at DESC
            LIMIT 200
        """)
        rows = [dict(r) for r in cur.fetchall()]
    return {"alerts": rows, "total": len(rows), "page": 1, "page_size": 200, "pages": 1}


def _query_poller(conn) -> dict:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, status, started_at, completed_at,
                   resources_found, resources_new, resources_updated,
                   resources_deleted, alerts_triggered, alerts_resolved,
                   error_log,
                   EXTRACT(EPOCH FROM (completed_at - started_at)) AS duration_seconds
            FROM poller_runs ORDER BY started_at DESC LIMIT 20
        """)
        runs = []
        for row in cur.fetchall():
            r = dict(row)
            if r.get("duration_seconds"):
                r["duration_seconds"] = round(float(r["duration_seconds"]), 1)
            runs.append(r)
    return {"runs": runs, "total": len(runs)}


# ---------------------------------------------------------------------------
# HTML page builder
# ---------------------------------------------------------------------------

def _build_page(
    title: str,
    active_page: str,
    snapshot_time: str,
    snapshot_data: dict,
    css: str,
    utils_js: str,
    page_js: str,
    body_html: str,
) -> str:
    """
    Build a fully self-contained snapshot HTML page.
    All CSS and JS inlined. Data embedded as window.__SNAPSHOT_DATA__.
    """
    data_json = _to_json(snapshot_data)

    nav_items = [
        ("overview",  "Overview",       "M3 3h7v7H3V3zm0 11h7v7H3v-7zm11-11h7v7h-7V3zm0 11h7v7h-7v-7z"),
        ("resources", "Resources",      "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"),
        ("alerts",    "Alerts",         "M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0"),
        ("poller",    "Poller Status",  "M23 4 23 10 17 10M1 20 1 14 7 14M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"),
    ]

    nav_html = ""
    for page_key, label, _ in nav_items:
        active_cls = "active" if page_key == active_page else ""
        nav_html += f'''
        <a href="{page_key}.html" class="nav-item {active_cls}">
          <span class="nav-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round">
              <path d="{_}"/>
            </svg>
          </span>
          <span>{label}</span>
        </a>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — AWS Resource Tracker</title>
  <style>{css}</style>
</head>
<body>

  <div class="snapshot-banner">
    <span>⚠️  Snapshot — Last updated {snapshot_time}</span>
    <span>This is not live data. Start your EC2 instance for the live dashboard.</span>
  </div>

  <div class="app-layout" style="padding-top:44px">
    <aside class="sidebar" style="top:44px">
      <div class="sidebar-logo">
        <div class="logo-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
        </div>
        <div class="logo-text">
          <span class="logo-title">AWS TRACKER</span>
          <span class="logo-version">v0.1.0 · snapshot</span>
        </div>
      </div>
      <div class="sidebar-divider"></div>
      <nav class="sidebar-nav">{nav_html}</nav>
      <div class="sidebar-divider"></div>
      <div class="sidebar-meta">
        <div class="meta-section">
          <span class="meta-label">Snapshot</span>
          <span class="meta-value" style="font-size:0.72rem">{snapshot_time}</span>
        </div>
      </div>
    </aside>

    <main class="main-content">
      {body_html}
    </main>
  </div>

  <script>
    // Embed all dashboard data for snapshot mode
    window.__SNAPSHOT_DATA__ = {data_json};
  </script>
  <script>{utils_js}</script>
  <script>{page_js}</script>

</body>
</html>'''


# ---------------------------------------------------------------------------
# Body HTML per page — same structure as live templates
# ---------------------------------------------------------------------------

def _overview_body() -> str:
    return '''
<div class="page-header">
  <div>
    <div class="page-title">Overview</div>
    <div class="page-subtitle">Your AWS environment at a glance</div>
  </div>
</div>

<div class="stat-grid">
  <div class="card" id="card-resources">
    <div class="card-accent-line"></div>
    <div class="card-label">Total Resources</div>
    <div class="card-value" id="stat-resources">—</div>
    <div class="card-sub" id="stat-resources-sub">Loading...</div>
  </div>
  <div class="card" id="card-alerts">
    <div class="card-accent-line"></div>
    <div class="card-label">Active Alerts</div>
    <div class="card-value" id="stat-alerts">—</div>
    <div class="card-sub" id="stat-alerts-sub">Loading...</div>
  </div>
  <div class="card" id="card-cost">
    <div class="card-accent-line"></div>
    <div class="card-label">Est. Total Cost</div>
    <div class="card-value mono" id="stat-cost">—</div>
    <div class="card-sub">On-demand pricing only</div>
  </div>
  <div class="card" id="card-poll">
    <div class="card-accent-line"></div>
    <div class="card-label">Last Poll</div>
    <div class="card-value" id="stat-poll-status" style="font-size:1.2rem">—</div>
    <div class="card-sub" id="stat-poll-sub">Loading...</div>
  </div>
</div>

<div style="display:grid;grid-template-columns:1.4fr 1fr;gap:20px">
  <div class="card">
    <div class="card-accent-line"></div>
    <div class="section-header">Resources by Type</div>
    <div id="resource-bars">
      <div style="display:flex;flex-direction:column;gap:10px">
        <div class="skeleton skeleton-text" style="width:100%;height:24px"></div>
      </div>
    </div>
  </div>
  <div class="card">
    <div class="card-accent-line"></div>
    <div class="section-header">Active Alerts</div>
    <div id="alert-summary">
      <div class="skeleton skeleton-text" style="width:100%;height:54px"></div>
    </div>
    <div id="view-all-alerts" style="display:none;margin-top:12px">
      <a href="alerts.html" class="btn btn-ghost btn-sm"
         style="width:100%;justify-content:center">View all alerts →</a>
    </div>
  </div>
</div>'''


def _resources_body() -> str:
    return '''
<div class="page-header">
  <div>
    <div class="page-title">Resources</div>
    <div class="page-subtitle" id="resources-subtitle">Loading...</div>
  </div>
</div>

<div class="filter-bar">
  <select class="filter-select" id="filter-type" onchange="applyFilters()">
    <option value="">All Types</option>
    <option value="ec2">EC2</option>
    <option value="rds">RDS</option>
    <option value="s3">S3</option>
    <option value="ebs_volume">EBS Volume</option>
    <option value="ebs_snapshot">EBS Snapshot</option>
    <option value="elastic_ip">Elastic IP</option>
    <option value="security_group">Security Group</option>
    <option value="iam_user">IAM User</option>
    <option value="cloudwatch_alarm">CloudWatch Alarm</option>
    <option value="rds_snapshot">RDS Snapshot</option>
  </select>
  <select class="filter-select" id="filter-state" onchange="applyFilters()">
    <option value="">All States</option>
    <option value="running">Running</option>
    <option value="stopped">Stopped</option>
    <option value="available">Available</option>
    <option value="in-use">In Use</option>
    <option value="unused">Unused</option>
    <option value="active">Active</option>
    <option value="inactive">Inactive</option>
  </select>
  <select class="filter-select" id="filter-region" onchange="applyFilters()">
    <option value="">All Regions</option>
    <option value="ap-south-1">ap-south-1</option>
    <option value="us-east-1">us-east-1</option>
    <option value="global">global</option>
  </select>
  <input type="text" class="search-input" id="search-input"
         placeholder="Search by name or ID..."
         oninput="handleSearch(this.value)">
</div>

<div class="table-container">
  <table class="data-table">
    <thead>
      <tr>
        <th onclick="sortBy(\'resource_type\')">Type</th>
        <th onclick="sortBy(\'resource_name\')">Name</th>
        <th onclick="sortBy(\'state\')">State</th>
        <th onclick="sortBy(\'region\')">Region</th>
        <th onclick="sortBy(\'created_at\')">Age</th>
        <th onclick="sortBy(\'estimated_cost_usd\')">Est. Cost</th>
        <th>Tags</th>
        <th></th>
      </tr>
    </thead>
    <tbody id="resources-tbody">
      <tr><td colspan="8">
        <div style="padding:16px">
          <div class="skeleton skeleton-text" style="width:100%;height:18px"></div>
        </div>
      </td></tr>
    </tbody>
  </table>
  <div class="table-footer">
    <span id="resources-count">Loading...</span>
    <div class="pagination" id="pagination"></div>
  </div>
</div>'''


def _alerts_body() -> str:
    return '''
<div class="page-header">
  <div>
    <div class="page-title">Alerts</div>
    <div class="page-subtitle" id="alerts-subtitle">Loading...</div>
  </div>
</div>

<div class="filter-bar">
  <select class="filter-select" id="filter-status" onchange="loadAlerts()">
    <option value="active">Active</option>
    <option value="resolved">Resolved</option>
    <option value="all">All</option>
  </select>
  <select class="filter-select" id="filter-severity" onchange="loadAlerts()">
    <option value="">All Severities</option>
    <option value="critical">Critical</option>
    <option value="warning">Warning</option>
    <option value="info">Info</option>
  </select>
  <select class="filter-select" id="filter-type" onchange="loadAlerts()">
    <option value="">All Types</option>
    <option value="security_group_unused">Security Group Unused</option>
    <option value="elastic_ip_unassociated">Elastic IP Unassociated</option>
    <option value="ec2_long_running">EC2 Long Running</option>
    <option value="ebs_unattached">EBS Unattached</option>
    <option value="iam_user_inactive">IAM User Inactive</option>
  </select>
</div>

<div class="table-container">
  <table class="data-table">
    <thead>
      <tr>
        <th>Severity</th><th>Resource</th><th>Alert Type</th>
        <th>Triggered</th><th>Status</th><th></th>
      </tr>
    </thead>
    <tbody id="alerts-tbody">
      <tr><td colspan="6">
        <div style="padding:16px">
          <div class="skeleton skeleton-text" style="width:100%;height:18px"></div>
        </div>
      </td></tr>
    </tbody>
  </table>
  <div class="table-footer">
    <span id="alerts-count">Loading...</span>
    <div class="pagination" id="alerts-pagination"></div>
  </div>
</div>'''


def _poller_body() -> str:
    return '''
<div class="page-header">
  <div>
    <div class="page-title">Poller Status</div>
    <div class="page-subtitle" id="poller-subtitle">Loading...</div>
  </div>
</div>

<div id="last-run-card" style="margin-bottom:24px">
  <div class="card skeleton" style="height:80px"></div>
</div>

<div class="table-container">
  <table class="data-table">
    <thead>
      <tr>
        <th>Run #</th><th>Started</th><th>Duration</th>
        <th>Found</th><th>New</th><th>Updated</th>
        <th>Deleted</th><th>Alerts</th><th>Status</th>
      </tr>
    </thead>
    <tbody id="poller-tbody">
      <tr><td colspan="9">
        <div style="padding:16px">
          <div class="skeleton skeleton-text" style="width:100%;height:18px"></div>
        </div>
      </td></tr>
    </tbody>
  </table>
  <div class="table-footer">
    <span id="poller-count">Loading...</span>
  </div>
</div>'''


# ---------------------------------------------------------------------------
# Snapshot-aware JS overrides
# These wrap the page JS to intercept apiFetch and serve from __SNAPSHOT_DATA__
# ---------------------------------------------------------------------------

_SNAPSHOT_UTILS_EXTRA = """
// ── Snapshot mode overrides ──
(function() {
  var _orig_apiFetch = apiFetch;

  function getSnapshotData(url) {
    var d = window.__SNAPSHOT_DATA__;
    if (!d) return null;
    if (url.includes('/api/overview'))   return d.overview   || null;
    if (url.includes('/api/resources'))  return d.resources  || null;
    if (url.includes('/api/alerts'))     return d.alerts     || null;
    if (url.includes('/api/poller'))     return d.poller     || null;
    return null;
  }

  window.apiFetch = async function(url) {
    if (window.__SNAPSHOT_DATA__) {
      return Promise.resolve(getSnapshotData(url));
    }
    return _orig_apiFetch(url);
  };

  window.apiPost = async function() {
    // No writes in snapshot mode
    return Promise.resolve({ success: false, error: 'Snapshot — read only' });
  };

  // Suppress sidebar data load in snapshot mode
  var _orig_sidebar = loadSidebarData;
  window.loadSidebarData = function() {
    if (window.__SNAPSHOT_DATA__) return;
    return _orig_sidebar();
  };
})();
"""


# ---------------------------------------------------------------------------
# Snapshot-aware resources JS — links go to .html files not /resources/...
# ---------------------------------------------------------------------------

_SNAPSHOT_RESOURCES_EXTRA = """
(function() {
  var _origRender = renderTable;
  // Patch row onclick to use .html links for snapshots
  window.renderTable = function() {
    _origRender();
    document.querySelectorAll('#resources-tbody tr[onclick]').forEach(function(tr) {
      var parts = tr.getAttribute('onclick').match(/\\/resources\\/([^/]+)\\/(.+)'/);
      if (parts) {
        tr.removeAttribute('onclick');
        tr.style.cursor = 'default';
      }
    });
  };
})();
"""


# ---------------------------------------------------------------------------
# Main generator function
# ---------------------------------------------------------------------------

def generate_snapshot(conn) -> dict:
    """
    Generate all snapshot pages.
    Returns dict: { 'index.html': html, 'resources.html': html, ... }
    Returns empty dict on failure — never raises.
    """
    try:
        logger.info("Generating static snapshot")

        # Load assets
        css      = _load_css()
        utils_js = _load_js("utils.js")
        ov_js    = _load_js("overview.js")
        res_js   = _load_js("resources.js")
        al_js    = _load_js("alerts.js")
        po_js    = _load_js("poller.js")

        if not css:
            logger.warning("dashboard.css not found — snapshot will have no styles")

        # Query all data
        overview_data  = _query_overview(conn)
        resources_data = _query_resources(conn)
        alerts_data    = _query_alerts(conn)
        poller_data    = _query_poller(conn)

        # Active alerts subset for overview panel
        active_alerts = {
            "alerts": [a for a in alerts_data["alerts"] if not a.get("resolved_at")],
            "total":  sum(1 for a in alerts_data["alerts"] if not a.get("resolved_at")),
            "page": 1, "page_size": 100, "pages": 1,
        }

        # Full snapshot data bundle
        snapshot_data = {
            "overview":  overview_data,
            "resources": resources_data,
            "alerts":    alerts_data,
            "poller":    poller_data,
        }

        now = datetime.now(timezone.utc)
        snapshot_time = now.strftime("%B %d, %Y at %H:%M UTC")

        pages = {}

        # Overview — needs active_alerts data for alert panel
        ov_snapshot = dict(snapshot_data)
        ov_snapshot["alerts"] = active_alerts
        pages["index.html"] = _build_page(
            title="Overview",
            active_page="overview",
            snapshot_time=snapshot_time,
            snapshot_data=ov_snapshot,
            css=css,
            utils_js=utils_js + _SNAPSHOT_UTILS_EXTRA,
            page_js=ov_js,
            body_html=_overview_body(),
        )

        # Resources
        pages["resources.html"] = _build_page(
            title="Resources",
            active_page="resources",
            snapshot_time=snapshot_time,
            snapshot_data=snapshot_data,
            css=css,
            utils_js=utils_js + _SNAPSHOT_UTILS_EXTRA,
            page_js=res_js + _SNAPSHOT_RESOURCES_EXTRA,
            body_html=_resources_body(),
        )

        # Alerts
        pages["alerts.html"] = _build_page(
            title="Alerts",
            active_page="alerts",
            snapshot_time=snapshot_time,
            snapshot_data=snapshot_data,
            css=css,
            utils_js=utils_js + _SNAPSHOT_UTILS_EXTRA,
            page_js=al_js,
            body_html=_alerts_body(),
        )

        # Poller
        pages["poller.html"] = _build_page(
            title="Poller Status",
            active_page="poller",
            snapshot_time=snapshot_time,
            snapshot_data=snapshot_data,
            css=css,
            utils_js=utils_js + _SNAPSHOT_UTILS_EXTRA,
            page_js=po_js,
            body_html=_poller_body(),
        )

        logger.info(f"Snapshot generated — {len(pages)} pages")
        return pages

    except Exception as e:
        logger.error(f"Snapshot generation failed: {e}", exc_info=True)
        return {}