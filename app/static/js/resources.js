'use strict';

let allResources = [];
let filteredResources = [];
let currentPage = 1;
const PAGE_SIZE = 50;
let sortKey = 'created_at';
let sortDir = -1;
let activePanelKey = null;

function getUrlParam(key) {
  return new URLSearchParams(window.location.search).get(key) || '';
}

function resourceKey(resourceType, resourceId) {
  return `${resourceType}::${resourceId}`;
}

function findResource(resourceType, resourceId) {
  return allResources.find((r) => r.resource_type === resourceType && r.resource_id === resourceId) || null;
}

async function loadResources() {
  const data = await apiFetch('/api/resources?page_size=500');
  if (!data) return;
  allResources = data.resources || [];
  const typeParam = getUrlParam('type');
  if (typeParam) { const sel = document.getElementById('filter-type'); if (sel) sel.value = typeParam; }
  applyFilters();
  document.getElementById('resources-subtitle').textContent = `${allResources.length} resources tracked`;
}

function applyFilters() {
  const type   = document.getElementById('filter-type')?.value   || '';
  const state  = document.getElementById('filter-state')?.value  || '';
  const region = document.getElementById('filter-region')?.value || '';
  const search = (document.getElementById('search-input')?.value || '').toLowerCase();

  filteredResources = allResources.filter(r => {
    if (type   && r.resource_type !== type)  return false;
    if (state) {
      const resourceState = (r.state || '').toLowerCase();
      if (resourceState !== state.toLowerCase()) return false;
    }
    if (region && r.region !== region)        return false;
    if (search) {
      const hay = `${r.resource_name} ${r.resource_id} ${r.resource_type}`.toLowerCase();
      if (!hay.includes(search)) return false;
    }
    return true;
  });
  currentPage = 1;
  sortResources();
  renderTable();
}

const handleSearch = debounce(applyFilters, 200);

function sortBy(key) {
  if (sortKey === key) sortDir *= -1; else { sortKey = key; sortDir = -1; }
  document.querySelectorAll('.data-table thead th').forEach(th => th.classList.remove('sorted'));
  const idx = ['resource_type','resource_name','state','region','created_at','estimated_cost_usd'].indexOf(key);
  if (idx >= 0) document.querySelectorAll('.data-table thead th')[idx]?.classList.add('sorted');
  sortResources(); renderTable();
}

function sortResources() {
  filteredResources.sort((a, b) => {
    let va = a[sortKey] ?? '', vb = b[sortKey] ?? '';
    if (sortKey === 'estimated_cost_usd') { va = parseFloat(va)||0; vb = parseFloat(vb)||0; }
    else if (sortKey === 'created_at') { va = va ? new Date(va).getTime():0; vb = vb ? new Date(vb).getTime():0; }
    else { va = String(va).toLowerCase(); vb = String(vb).toLowerCase(); }
    return va < vb ? -1*sortDir : va > vb ? 1*sortDir : 0;
  });
}

function renderTable() {
  const tbody = document.getElementById('resources-tbody');
  const page  = filteredResources.slice((currentPage-1)*PAGE_SIZE, currentPage*PAGE_SIZE);

  if (page.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8"><div class="empty-state"><div class="empty-state-icon">⬚</div><div class="empty-state-title">No resources found</div><div class="empty-state-sub">Try adjusting your filters</div></div></td></tr>`;
  } else {
    tbody.innerHTML = page.map((r, i) => {
      const tagsHtml = r.tags && Object.keys(r.tags).length > 0
        ? Object.entries(r.tags).slice(0,2).map(([k,v]) =>
            `<span class="tag-pill" title="${esc(`${k}:${v}`)}"><span class="tag-key">${esc(k)}</span><span style="color:var(--text-dim)">:</span><span class="tag-val">${esc(trunc(v,16))}</span></span>`
          ).join(' ')
        : '<span style="color:var(--text-dim);font-size:0.7rem">—</span>';

      return `
        <tr class="${stateRowClass(r.state)}"
            style="animation:fadeInUp 0.2s ease forwards;animation-delay:${Math.min(i*0.02,0.3)}s"
            data-resource-type="${esc(r.resource_type)}"
            data-resource-id="${esc(r.resource_id)}"
            tabindex="0"
            aria-label="View details for ${esc(r.resource_name || r.resource_id)}">
          <td>${typeBadge(r.resource_type)}</td>
          <td>
            <div style="font-weight:500;color:var(--text-primary)">${esc(trunc(r.resource_name||r.resource_id,32))}</div>
            <div class="resource-id">${esc(trunc(r.resource_id,32))}</div>
          </td>
          <td><span class="state-dot ${esc(stateClass(r.state))}">${esc(r.state||'—')}</span></td>
          <td><span class="mono" style="color:var(--text-secondary)">${esc(r.region||'—')}</span></td>
          <td><span title="${esc(r.created_at||'')}" style="color:var(--text-secondary)">${ageFromISO(r.created_at)}</span></td>
          <td><span class="${costClass(r.estimated_cost_usd)}">${formatCost(r.estimated_cost_usd)}</span></td>
          <td><div style="display:flex;gap:4px;flex-wrap:wrap">${tagsHtml}</div></td>
          <td><button type="button" class="text-link-btn">View</button></td>
        </tr>`;
    }).join('');
    bindRowInteractions();
  }

  const total = filteredResources.length;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  document.getElementById('resources-count').textContent = `${total} resource${total!==1?'s':''}`;

  const pg = document.getElementById('pagination');
  if (pages <= 1) { pg.innerHTML = ''; return; }
  let btns = `<button class="page-btn" ${currentPage===1?'disabled':''} onclick="goPage(${currentPage-1})">‹</button>`;
  for (let p=1; p<=pages; p++) {
    if (p===1||p===pages||Math.abs(p-currentPage)<=1) btns += `<button class="page-btn${p===currentPage?' active':''}" onclick="goPage(${p})">${p}</button>`;
    else if (Math.abs(p-currentPage)===2) btns += `<span style="color:var(--text-dim);padding:0 4px">…</span>`;
  }
  btns += `<button class="page-btn" ${currentPage===pages?'disabled':''} onclick="goPage(${currentPage+1})">›</button>`;
  pg.innerHTML = btns;
}

function goPage(p) {
  currentPage = Math.max(1, Math.min(p, Math.ceil(filteredResources.length/PAGE_SIZE)));
  renderTable();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function bindRowInteractions() {
  const rows = document.querySelectorAll('#resources-tbody tr[data-resource-type]');
  rows.forEach((row) => {
    const open = () => openResourcePanel(row.dataset.resourceType, row.dataset.resourceId);
    row.addEventListener('click', open);
    row.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        open();
      }
    });

    row.querySelectorAll('.text-link-btn').forEach((btn) => {
      btn.addEventListener('click', (event) => {
        event.stopPropagation();
        open();
      });
    });
  });
}

async function fetchResourceDetail(resourceType, resourceId) {
  const data = await apiFetch(
    `/api/resources/${encodeURIComponent(resourceType)}/${encodeURIComponent(resourceId)}`
  );
  if (data && data.resource) return data;

  const fallbackResource = findResource(resourceType, resourceId);
  if (!fallbackResource) return null;

  const snapshotAlerts = window.__SNAPSHOT_DATA__?.alerts?.alerts || [];
  const relatedAlerts = snapshotAlerts
    .filter((a) => a.resource_type === resourceType && a.resource_id === resourceId)
    .slice(0, 10);

  return {
    resource: fallbackResource,
    snapshots: [],
    alerts: relatedAlerts,
  };
}

function openResourcePanelShell() {
  const panel = document.getElementById('resource-detail-panel');
  const backdrop = document.getElementById('resource-panel-backdrop');
  panel?.classList.add('open');
  backdrop?.classList.add('open');
  panel?.setAttribute('aria-hidden', 'false');
  document.body.classList.add('panel-open');
}

function closeResourcePanel() {
  const panel = document.getElementById('resource-detail-panel');
  const backdrop = document.getElementById('resource-panel-backdrop');
  panel?.classList.remove('open');
  backdrop?.classList.remove('open');
  panel?.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('panel-open');
  activePanelKey = null;
}

async function openResourcePanel(resourceType, resourceId) {
  activePanelKey = resourceKey(resourceType, resourceId);
  openResourcePanelShell();

  const titleEl = document.getElementById('resource-panel-title');
  const metaEl = document.getElementById('resource-panel-meta');
  const highlightsEl = document.getElementById('resource-panel-highlights');
  const tagsEl = document.getElementById('resource-panel-tags');
  const alertsEl = document.getElementById('resource-panel-alerts');
  const timelineEl = document.getElementById('resource-panel-timeline');
  const fullLinkEl = document.getElementById('resource-panel-full-link');

  titleEl.textContent = 'Loading Resource...';
  metaEl.textContent = `${formatTypeLabel(resourceType)} · ${trunc(resourceId, 42)}`;
  highlightsEl.innerHTML = '<div class="skeleton skeleton-text" style="height:70px;width:100%"></div>';
  tagsEl.innerHTML = '<div class="skeleton skeleton-text" style="height:22px;width:85%"></div>';
  alertsEl.innerHTML = '<div class="skeleton skeleton-text" style="height:22px;width:100%"></div>';
  timelineEl.innerHTML = '<div class="skeleton skeleton-text" style="height:16px;width:100%"></div>';
  if (fullLinkEl) {
    fullLinkEl.href = `/resources/${encodeURIComponent(resourceType)}/${encodeURIComponent(resourceId)}`;
  }

  const data = await fetchResourceDetail(resourceType, resourceId);
  if (!data) {
    titleEl.textContent = 'Resource not found';
    metaEl.textContent = 'Unable to load details for selected resource';
    highlightsEl.innerHTML = '';
    tagsEl.innerHTML = '<div class="empty-state" style="padding:12px 0">No data available</div>';
    alertsEl.innerHTML = '';
    timelineEl.innerHTML = '';
    return;
  }

  if (activePanelKey !== resourceKey(resourceType, resourceId)) return;

  renderResourcePanel(data);
}

function renderResourcePanel(data) {
  const { resource, snapshots = [], alerts = [] } = data;
  const titleEl = document.getElementById('resource-panel-title');
  const metaEl = document.getElementById('resource-panel-meta');
  const highlightsEl = document.getElementById('resource-panel-highlights');
  const tagsEl = document.getElementById('resource-panel-tags');
  const alertsEl = document.getElementById('resource-panel-alerts');
  const timelineEl = document.getElementById('resource-panel-timeline');

  titleEl.innerHTML = `${typeBadge(resource.resource_type)} <span style="margin-left:8px">${esc(resource.resource_name || resource.resource_id)}</span>`;
  metaEl.innerHTML = `<span class="resource-id">${esc(resource.resource_id)}</span> · ${esc(resource.region || '—')} · ${esc(resource.account_id || '—')} · <span class="state-dot ${esc(stateClass(resource.state))}">${esc(resource.state || '—')}</span>`;

  highlightsEl.innerHTML = `
    <div class="detail-kpi-grid">
      <div class="detail-kpi-card">
        <div class="detail-kpi-label">Age</div>
        <div class="detail-kpi-value">${ageFromISO(resource.created_at)}</div>
      </div>
      <div class="detail-kpi-card">
        <div class="detail-kpi-label">Estimated Cost</div>
        <div class="detail-kpi-value ${costClass(resource.estimated_cost_usd)}">${formatCost(resource.estimated_cost_usd)}</div>
      </div>
      <div class="detail-kpi-card">
        <div class="detail-kpi-label">First Seen</div>
        <div class="detail-kpi-value">${formatDate(resource.first_seen)}</div>
      </div>
      <div class="detail-kpi-card">
        <div class="detail-kpi-label">Last Seen</div>
        <div class="detail-kpi-value">${relativeTime(resource.last_seen)}</div>
      </div>
    </div>`;

  if (resource.tags && Object.keys(resource.tags).length > 0) {
    tagsEl.innerHTML = `<div style="display:flex;flex-wrap:wrap;gap:6px">${renderTags(resource.tags)}</div>`;
  } else {
    tagsEl.innerHTML = '<div class="empty-state" style="padding:12px 0">No tags on this resource</div>';
  }

  if (alerts.length === 0) {
    alertsEl.innerHTML = '<div class="all-clear" style="justify-content:flex-start;padding:8px 0">No alerts for this resource</div>';
  } else {
    alertsEl.innerHTML = alerts.slice(0, 6).map((a) => `
      <div class="alert-summary-item ${a.severity}" style="margin-bottom:8px;flex-direction:column;gap:6px;cursor:default">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          ${severityBadge(a.severity)}
          <span style="font-size:0.78rem;color:var(--text-primary);font-weight:500">${esc(a.alert_type.replace(/_/g,' '))}</span>
          <span style="font-size:0.7rem;color:var(--text-dim);margin-left:auto">${relativeTime(a.triggered_at)}</span>
        </div>
        <div style="font-size:0.76rem;color:var(--text-secondary);line-height:1.5">${esc(a.message || '')}</div>
      </div>
    `).join('');
  }

  if (!snapshots.length) {
    timelineEl.innerHTML = '<div class="empty-state" style="padding:12px 0">Snapshot timeline not available for this view yet</div>';
    return;
  }

  const rendered = [];
  let prevState = null;
  let prevTags = null;
  snapshots.forEach((snap, i) => {
    const isFirst = i === 0;
    const isLast = i === snapshots.length - 1;
    const stateChanged = snap.state !== prevState;
    const tagsChanged = JSON.stringify(snap.tags) !== prevTags;
    if (isFirst || isLast || stateChanged || tagsChanged) {
      const badges = [];
      if (isFirst) badges.push('<span class="timeline-badge new">FIRST</span>');
      if (stateChanged && !isFirst) badges.push('<span class="timeline-badge change">STATE</span>');
      if (tagsChanged && !isFirst) badges.push('<span class="timeline-badge change">TAGS</span>');
      rendered.push({ snap, badges, isLast, idx: rendered.length });
    }
    prevState = snap.state;
    prevTags = JSON.stringify(snap.tags);
  });

  timelineEl.innerHTML = rendered.map((item) => `
    <div class="timeline-item ${item.isLast ? 'latest' : ''}" style="--i:${item.idx}">
      <div class="timeline-time">${formatDate(item.snap.polled_at)}</div>
      <div class="timeline-content">
        <span class="state-dot ${esc(stateClass(item.snap.state))}">${esc(item.snap.state || '—')}</span>
        ${item.badges.join('')}
        ${item.isLast ? '<span style="font-size:0.7rem;color:var(--accent)">CURRENT</span>' : ''}
      </div>
    </div>
  `).join('');
}

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeResourcePanel();
});

document.addEventListener('DOMContentLoaded', loadResources);