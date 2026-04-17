'use strict';

let lastLoadedRuns = [];

async function loadPollerStatus() {
  const data = await apiFetch('/api/poller');
  if (!data) return;

  const runs = data.runs || [];
  lastLoadedRuns = runs;
  const last = runs[0];

  if (last) {
    const statusMap = {
      success:        { label:'✓ SUCCESS',         color:'var(--success)',  bg:'var(--success-bg)' },
      partial_failure:{ label:'⚠ PARTIAL FAILURE', color:'var(--warning)',  bg:'var(--warning-bg)' },
      failed:         { label:'✗ FAILED',           color:'var(--critical)', bg:'var(--critical-bg)' },
      running:        { label:'⟳ RUNNING',          color:'var(--info)',     bg:'var(--info-bg)' },
    };
    const s = statusMap[last.status] || { label:last.status, color:'var(--text-secondary)', bg:'var(--bg-elevated)' };
    document.getElementById('last-run-card').innerHTML = `
      <div class="card" style="border-color:${s.color}22">
        <div class="card-accent-line" style="background:linear-gradient(90deg,${s.color},transparent);opacity:1"></div>
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
          <div>
            <div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-dim);margin-bottom:6px">Last Run</div>
            <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
              <span style="font-family:var(--font-display);font-size:1.1rem;font-weight:700;color:${s.color}">${s.label}</span>
              <span style="color:var(--text-secondary);font-size:0.85rem">run #${last.id}</span>
              <span style="color:var(--text-dim)">·</span>
              <span title="${esc(last.started_at)}" style="color:var(--text-secondary);font-size:0.85rem">${relativeTime(last.started_at)}</span>
              ${last.duration_seconds?`<span style="color:var(--text-dim)">·</span><span class="mono" style="font-size:0.8rem;color:var(--text-secondary)">${last.duration_seconds}s</span>`:''}
            </div>
          </div>
          <div style="display:flex;gap:20px;flex-wrap:wrap">
            ${[['FOUND',last.resources_found,'var(--text-secondary)'],['NEW',last.resources_new,'var(--success)'],['UPDATED',last.resources_updated,'var(--info)'],['DELETED',last.resources_deleted,last.resources_deleted>0?'var(--warning)':'var(--text-dim)'],['ALERTS',last.alerts_triggered,last.alerts_triggered>0?'var(--warning)':'var(--text-dim)']].map(([l,v,c])=>`
              <div style="text-align:center">
                <div style="font-size:0.6rem;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-dim)">${l}</div>
                <div class="mono" style="font-size:1.1rem;font-weight:600;color:${c}">${v??0}</div>
              </div>`).join('')}
          </div>
        </div>
      </div>`;
  }

  const sub = document.getElementById('poller-subtitle');
  if (sub) sub.textContent = `${runs.length} recent run${runs.length!==1?'s':''}`;
  document.getElementById('poller-count').textContent = `${runs.length} runs`;

  const tbody = document.getElementById('poller-tbody');
  if (runs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9"><div class="empty-state"><div class="empty-state-icon">⟳</div><div class="empty-state-title">No poll runs yet</div></div></td></tr>`;
    return;
  }

  const statusMap = { success:{icon:'✓',cls:'success'}, partial_failure:{icon:'⚠',cls:'partial_failure'}, failed:{icon:'✗',cls:'failed'}, running:{icon:'⟳',cls:'running'} };
  tbody.innerHTML = runs.map((run, i) => {
    const s = statusMap[run.status] || { icon:'?', cls:'' };
    const hasError = !!run.error_log;
    const rowClass = run.status==='failed'?'state-critical':run.status==='partial_failure'?'state-warning':'';
    return `
      <tr class="${rowClass}" style="animation:fadeInUp 0.2s ease forwards;animation-delay:${Math.min(i*0.03,0.4)}s"
          data-run-id="${run.id}"
          tabindex="0"
          aria-label="Inspect run ${run.id}">
        <td><span class="mono" style="color:var(--accent)">#${run.id}</span></td>
        <td><span title="${esc(run.started_at)}" style="color:var(--text-secondary);font-size:0.8rem">${formatDate(run.started_at)}</span></td>
        <td><span class="mono" style="font-size:0.78rem;color:var(--text-secondary)">${run.duration_seconds!=null?run.duration_seconds+'s':'—'}</span></td>
        <td><span class="mono" style="color:var(--text-primary)">${run.resources_found??0}</span></td>
        <td><span class="mono" style="color:${run.resources_new>0?'var(--success)':'var(--text-dim)'}">${run.resources_new??0}</span></td>
        <td><span class="mono" style="color:var(--text-secondary)">${run.resources_updated??0}</span></td>
        <td><span class="mono" style="color:${run.resources_deleted>0?'var(--warning)':'var(--text-dim)'}">${run.resources_deleted??0}</span></td>
        <td><span class="mono" style="color:${run.alerts_triggered>0?'var(--warning)':'var(--text-dim)'}">${run.alerts_triggered??0}</span></td>
        <td>
          <span class="run-status ${s.cls}">${s.icon} ${run.status}</span>
          ${hasError?`<button type="button" class="text-link-btn" onclick="toggleErrorLog(event, ${run.id})">log</button>`:''}
        </td>
      </tr>
      ${hasError?`<tr id="err-${run.id}" style="display:none"><td colspan="9"><div style="padding:12px 16px"><div class="error-log">${esc(run.error_log)}</div></div></td></tr>`:''}`;
  }).join('');

  bindRunRowInteractions();
}

function toggleErrorLog(event, runId) {
  if (event) event.stopPropagation();
  const row = document.getElementById(`err-${runId}`);
  if (row) row.style.display = row.style.display === 'none' ? '' : 'none';
}

function bindRunRowInteractions() {
  const rows = document.querySelectorAll('#poller-tbody tr[data-run-id]');
  rows.forEach((row) => {
    const open = () => openRunPanel(Number(row.dataset.runId));
    row.addEventListener('click', open);
    row.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        open();
      }
    });
  });
}

function openRunPanelShell() {
  const panel = document.getElementById('run-detail-panel');
  const backdrop = document.getElementById('run-panel-backdrop');
  panel?.classList.add('open');
  backdrop?.classList.add('open');
  panel?.setAttribute('aria-hidden', 'false');
  document.body.classList.add('panel-open');
}

function closeRunPanel() {
  const panel = document.getElementById('run-detail-panel');
  const backdrop = document.getElementById('run-panel-backdrop');
  panel?.classList.remove('open');
  backdrop?.classList.remove('open');
  panel?.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('panel-open');
}

async function openRunPanel(runId) {
  openRunPanelShell();
  const titleEl = document.getElementById('run-panel-title');
  const metaEl = document.getElementById('run-panel-meta');
  const summaryEl = document.getElementById('run-panel-summary');
  const createdEl = document.getElementById('run-panel-created');
  const updatedEl = document.getElementById('run-panel-updated');
  const deletedEl = document.getElementById('run-panel-deleted');
  const existingEl = document.getElementById('run-panel-existing');

  titleEl.textContent = `Run #${runId} Resource Map`;
  metaEl.textContent = 'Loading run details...';
  summaryEl.innerHTML = '<div class="skeleton skeleton-text" style="height:70px;width:100%"></div>';
  createdEl.innerHTML = '<div class="skeleton skeleton-text" style="height:22px;width:85%"></div>';
  updatedEl.innerHTML = '<div class="skeleton skeleton-text" style="height:22px;width:85%"></div>';
  deletedEl.innerHTML = '<div class="skeleton skeleton-text" style="height:22px;width:85%"></div>';
  existingEl.innerHTML = '<div class="skeleton skeleton-text" style="height:22px;width:85%"></div>';

  const data = await apiFetch(`/api/poller/${runId}/resource-map`);
  if (!data || !data.run || !data.categories) {
    const fallback = lastLoadedRuns.find((r) => r.id === runId);
    metaEl.textContent = fallback
      ? `${formatDate(fallback.started_at)} · ${fallback.status}`
      : 'Could not load resource map for this run';
    summaryEl.innerHTML = '<div class="empty-state" style="padding:10px 0">Run map is unavailable in this mode.</div>';
    createdEl.innerHTML = '';
    updatedEl.innerHTML = '';
    deletedEl.innerHTML = '';
    existingEl.innerHTML = '';
    return;
  }

  renderRunPanel(data);
}

function renderRunPanel(data) {
  const run = data.run;
  const previous = data.previous_run;
  const categories = data.categories;

  const metaEl = document.getElementById('run-panel-meta');
  const summaryEl = document.getElementById('run-panel-summary');
  metaEl.textContent = `${formatDate(run.started_at)} · ${run.status}`;

  summaryEl.innerHTML = `
    <div class="detail-kpi-grid">
      <div class="detail-kpi-card"><div class="detail-kpi-label">Found</div><div class="detail-kpi-value">${run.resources_found ?? 0}</div></div>
      <div class="detail-kpi-card"><div class="detail-kpi-label">New</div><div class="detail-kpi-value" style="color:var(--success)">${categories.created.total}</div></div>
      <div class="detail-kpi-card"><div class="detail-kpi-label">Updated</div><div class="detail-kpi-value" style="color:var(--info)">${categories.updated.total}</div></div>
      <div class="detail-kpi-card"><div class="detail-kpi-label">Deleted</div><div class="detail-kpi-value" style="color:${categories.deleted.total > 0 ? 'var(--warning)' : 'var(--text-secondary)'}">${categories.deleted.total}</div></div>
      <div class="detail-kpi-card"><div class="detail-kpi-label">Existing</div><div class="detail-kpi-value">${categories.existing.total}</div></div>
      <div class="detail-kpi-card"><div class="detail-kpi-label">Compared To</div><div class="detail-kpi-value">${previous ? `Run #${previous.id}` : 'No previous run'}</div></div>
    </div>`;

  renderRunCategory('run-panel-created', categories.created, 'No resources created in this run');
  renderRunCategory('run-panel-updated', categories.updated, 'No resources updated in this run');
  renderRunCategory('run-panel-deleted', categories.deleted, 'No resources deleted in this run');
  renderRunCategory('run-panel-existing', categories.existing, 'No existing resources tracked in this run');
}

function renderRunCategory(containerId, category, emptyMessage) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const byType = category?.by_type || [];
  const items = category?.items || [];

  if (!items.length) {
    el.innerHTML = `<div class="empty-state" style="padding:10px 0">${emptyMessage}</div>`;
    return;
  }

  const summaryPills = byType
    .slice(0, 8)
    .map((entry) => `<span class="tag-pill">${formatTypeLabel(entry.resource_type)}: ${entry.count}</span>`)
    .join(' ');

  const rows = items
    .slice(0, 14)
    .map(
      (item) => `
      <div class="run-map-item">
        <div style="min-width:0;flex:1">
          <div class="name">${esc(item.resource_name || item.resource_id)}</div>
          <div class="meta">${esc(item.resource_id)} · ${esc(item.region || '—')}</div>
        </div>
        ${typeBadge(item.resource_type)}
      </div>`
    )
    .join('');

  const remaining = Math.max((category.total || 0) - 14, 0);
  el.innerHTML = `
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px">${summaryPills}</div>
    <div class="run-map-list">${rows}</div>
    ${remaining ? `<div style="margin-top:8px;color:var(--text-dim);font-size:0.72rem">+${remaining} more resources in this category</div>` : ''}
  `;
}

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeRunPanel();
});

document.addEventListener('DOMContentLoaded', loadPollerStatus);