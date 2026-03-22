'use strict';

async function loadDetail() {
  const type = window.RESOURCE_TYPE;
  const id   = window.RESOURCE_ID;
  if (!type || !id) return;

  const data = await apiFetch(`/api/resources/${encodeURIComponent(type)}/${encodeURIComponent(id)}`);
  if (!data) return;

  const r = data.resource;
  const snapshots = data.snapshots || [];
  const alerts    = data.alerts    || [];

  document.getElementById('resource-header').innerHTML = `
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:6px">
      ${typeBadge(r.resource_type)}
      <span class="page-title" style="font-size:1.3rem">${esc(r.resource_name||r.resource_id)}</span>
      <span class="state-dot ${esc(stateClass(r.state))}" style="font-size:0.9rem">${esc(r.state||'—')}</span>
    </div>
    <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
      <span class="resource-id" style="font-size:0.8rem">${esc(r.resource_id)}</span>
      <span style="color:var(--text-dim)">·</span>
      <span class="mono" style="font-size:0.8rem;color:var(--text-secondary)">${esc(r.region)}</span>
      <span style="color:var(--text-dim)">·</span>
      <span style="font-size:0.8rem;color:var(--text-secondary)">account ${esc(r.account_id)}</span>
    </div>`;

  document.getElementById('detail-age').textContent = ageFromISO(r.created_at);
  const costEl = document.getElementById('detail-cost');
  costEl.textContent = formatCost(r.estimated_cost_usd);
  if (parseFloat(r.estimated_cost_usd) > 0) costEl.style.color = 'var(--warning)';
  document.getElementById('detail-first').innerHTML = `<span title="${esc(r.first_seen)}">${formatDate(r.first_seen)}</span>`;
  document.getElementById('detail-last').innerHTML  = `<span title="${esc(r.last_seen)}">${relativeTime(r.last_seen)}</span>`;

  document.getElementById('detail-tags').innerHTML =
    r.tags && Object.keys(r.tags).length > 0
      ? `<div style="display:flex;flex-wrap:wrap;gap:6px">${renderTags(r.tags)}</div>`
      : `<div class="empty-state" style="padding:16px"><div class="empty-state-icon">◌</div><div class="empty-state-sub">No tags on this resource</div></div>`;

  const alertContainer = document.getElementById('detail-alerts');
  if (alerts.length === 0) {
    alertContainer.innerHTML = `<div class="all-clear"><span style="font-size:1.2rem">✓</span><span>No alerts for this resource</span></div>`;
  } else {
    alertContainer.innerHTML = alerts.map(a => `
      <div class="alert-summary-item ${a.severity}" style="margin-bottom:8px;flex-direction:column;gap:6px">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          ${severityBadge(a.severity)}
          <span style="font-size:0.78rem;color:var(--text-primary);font-weight:500">${esc(a.alert_type.replace(/_/g,' '))}</span>
          <span style="font-size:0.7rem;color:var(--text-dim);margin-left:auto">${relativeTime(a.triggered_at)}</span>
          ${a.resolved_at
            ? `<span style="font-size:0.7rem;color:var(--success);padding:2px 6px;background:var(--success-bg);border-radius:3px">resolved</span>`
            : `<span style="font-size:0.7rem;color:var(--critical);padding:2px 6px;background:var(--critical-bg);border-radius:3px">open</span>`}
        </div>
        <div style="font-size:0.76rem;color:var(--text-secondary);line-height:1.5">${esc(a.message)}</div>
      </div>`).join('');
  }

  const tl = document.getElementById('detail-timeline');
  if (snapshots.length === 0) { tl.innerHTML = `<div style="color:var(--text-dim);font-size:0.8rem;padding:16px 0">No snapshots yet.</div>`; return; }

  const rendered = [];
  let prevState = null, prevTags = null;
  snapshots.forEach((snap, i) => {
    const isFirst = i === 0, isLast = i === snapshots.length - 1;
    const stateChanged = snap.state !== prevState;
    const tagsChanged  = JSON.stringify(snap.tags) !== prevTags;
    if (isFirst || isLast || stateChanged || tagsChanged) {
      const badges = [];
      if (isFirst) badges.push(`<span class="timeline-badge new">FIRST SEEN</span>`);
      if (stateChanged && !isFirst) badges.push(`<span class="timeline-badge change">STATE CHANGE</span>`);
      if (tagsChanged  && !isFirst) badges.push(`<span class="timeline-badge change">TAGS CHANGED</span>`);
      rendered.push({ polled_at:snap.polled_at, state:snap.state, cost:snap.estimated_cost_usd, badges, isLast, idx:rendered.length });
    }
    prevState = snap.state; prevTags = JSON.stringify(snap.tags);
  });

  tl.innerHTML = rendered.map(item => `
    <div class="timeline-item ${item.isLast?'latest':''}" style="--i:${item.idx}">
      <div class="timeline-time">${formatDate(item.polled_at)}</div>
      <div class="timeline-content">
        <span class="state-dot ${esc(stateClass(item.state))}">${esc(item.state||'—')}</span>
        ${item.badges.join('')}
        ${item.cost && parseFloat(item.cost) > 0 ? `<span class="cost-value has-cost">${formatCost(item.cost)}</span>` : ''}
        ${item.isLast ? `<span style="font-size:0.7rem;color:var(--accent);padding:1px 6px;background:var(--accent-dim);border-radius:3px">CURRENT</span>` : ''}
      </div>
    </div>`).join('');
}

document.addEventListener('DOMContentLoaded', loadDetail);