'use strict';

async function apiFetch(url) {
  try {
    const res = await fetch(url, { credentials: 'same-origin' });
    if (res.status === 401) { window.location.reload(); return null; }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error || res.statusText);
    }
    return await res.json();
  } catch (e) {
    console.error(`API error [${url}]:`, e);
    return null;
  }
}

async function apiPost(url) {
  try {
    const res = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error || res.statusText);
    }
    return await res.json();
  } catch (e) {
    console.error(`API POST error [${url}]:`, e);
    return null;
  }
}

function relativeTime(isoString) {
  if (!isoString) return '—';
  const diff = Date.now() - new Date(isoString).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60)   return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)   return `${m}min ago`;
  const h = Math.floor(m / 60);
  if (h < 24)   return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30)   return `${d}d ago`;
  return `${Math.floor(d / 30)}mo ago`;
}

function ageFromISO(isoString) {
  if (!isoString) return '—';
  const diff = Date.now() - new Date(isoString).getTime();
  const s = Math.floor(diff / 1000);
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  const d = Math.floor(h / 24);
  if (d > 0)  return `${d}d ${h % 24}h`;
  if (h > 0)  return `${h}h ${m % 60}m`;
  if (m > 0)  return `${m}m`;
  return `${s}s`;
}

function formatDate(isoString) {
  if (!isoString) return '—';
  const d = new Date(isoString);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}

function formatCost(val) {
  if (!val || val === 0 || parseFloat(val) === 0) return '—';
  const n = parseFloat(val);
  if (n < 0.01) return '<$0.01';
  return `$${n.toFixed(2)}`;
}

function costClass(val) {
  return (val && parseFloat(val) > 0) ? 'cost-value has-cost' : 'cost-value';
}

function stateClass(state) {
  if (!state) return 'unknown';
  const map = {
    running:'running', available:'available', active:'active',
    associated:'associated', ok:'OK', 'in-use':'in-use',
    stopped:'stopped', stopping:'stopping',
    unused:'unused', unassociated:'unassociated',
    error:'error', alarm:'ALARM', insufficient_data:'INSUFFICIENT_DATA',
    inactive:'inactive',
  };
  return map[state.toLowerCase()] || state.toLowerCase();
}

function stateRowClass(state) {
  if (!state) return '';
  const s = state.toLowerCase();
  if (['unused','unassociated','error','alarm'].includes(s)) return 'state-critical';
  if (['stopped','stopping','insufficient_data'].includes(s)) return 'state-warning';
  if (['running','available','active','associated','ok','in-use'].includes(s)) return 'state-success';
  return 'state-info';
}

function typeBadge(type) {
  if (!type) return '';
  const labels = { ec2:'EC2', rds:'RDS', s3:'S3', ebs_volume:'EBS', ebs_snapshot:'SNAP', elastic_ip:'EIP', security_group:'SG', iam_user:'IAM', cloudwatch_alarm:'CW', rds_snapshot:'RSNAP' };
  return `<span class="type-badge ${type}">${labels[type] || type.toUpperCase()}</span>`;
}

function renderTags(tags) {
  if (!tags || Object.keys(tags).length === 0)
    return '<span style="color:var(--text-dim);font-size:0.72rem">no tags</span>';
  return Object.entries(tags).map(([k,v]) =>
    `<span class="tag-pill"><span class="tag-key">${esc(k)}</span><span style="color:var(--text-dim)">:</span><span class="tag-val">${esc(v)}</span></span>`
  ).join(' ');
}

function severityBadge(severity) {
  const icons = { critical:'●', warning:'◐', info:'○' };
  return `<span class="severity-badge ${severity}">${icons[severity]||'○'} ${severity}</span>`;
}

function esc(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function animateCount(el, target, duration = 600) {
  const start = performance.now();
  function update(now) {
    const p = Math.min((now - start) / duration, 1);
    const e = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.floor(target * e);
    if (p < 1) requestAnimationFrame(update);
    else el.textContent = target;
  }
  requestAnimationFrame(update);
}

async function loadSidebarData() {
  const data = await apiFetch('/api/overview');
  if (!data) return;

  const el = document.getElementById('sidebar-last-poll');
  if (el && data.last_run) {
    const s = data.last_run.status;
    const color = s === 'success' ? 'var(--success)' : s === 'partial_failure' ? 'var(--warning)' : 'var(--critical)';
    el.innerHTML = `<span style="color:${color}">${relativeTime(data.last_run.completed_at || data.last_run.started_at)}</span>`;
  }

  const badge = document.getElementById('nav-alerts-badge');
  if (badge) {
    const c = data.total_alerts || 0;
    if (c > 0) { badge.textContent = c; badge.classList.add('alert-badge'); }
    else badge.textContent = '';
  }

  const resBadge = document.getElementById('nav-resources-badge');
  if (resBadge) resBadge.textContent = data.total_resources || '';

  const dot = document.getElementById('nav-poller-status');
  if (dot && data.last_run) {
    dot.className = 'nav-status';
    if (data.last_run.status === 'partial_failure') dot.classList.add('warning');
    else if (data.last_run.status !== 'success') dot.classList.add('error');
  }
}

function trunc(str, len = 28) {
  if (!str) return '—';
  return str.length > len ? str.slice(0, len) + '…' : str;
}

function debounce(fn, delay = 200) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), delay); };
}

document.addEventListener('DOMContentLoaded', () => { loadSidebarData(); });