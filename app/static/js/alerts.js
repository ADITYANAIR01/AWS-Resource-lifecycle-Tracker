'use strict';

let currentPage = 1;
const PAGE_SIZE = 50;
let totalAlerts = 0;

async function loadAlerts() { currentPage = 1; await fetchAlerts(); }

async function fetchAlerts() {
  const status   = document.getElementById('filter-status')?.value   || 'active';
  const severity = document.getElementById('filter-severity')?.value || '';
  const type     = document.getElementById('filter-type')?.value     || '';

  let url = `/api/alerts?status=${status}&page=${currentPage}`;
  if (severity) url += `&severity=${severity}`;
  if (type)     url += `&type=${type}`;

  const data = await apiFetch(url);
  if (!data) return;

  totalAlerts = data.total || 0;
  const sub = document.getElementById('alerts-subtitle');
  if (sub) sub.textContent = `${totalAlerts} alert${totalAlerts!==1?'s':''} ${status === 'all' ? 'total' : status}`;
  document.getElementById('alerts-count').textContent = `${totalAlerts} alert${totalAlerts!==1?'s':''}`;

  renderAlerts(data.alerts || [], data);
}

function renderAlerts(alerts, meta) {
  const tbody = document.getElementById('alerts-tbody');

  if (alerts.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-state-icon">◎</div><div class="empty-state-title">No alerts found</div><div class="empty-state-sub">Try changing the filters above</div></div></td></tr>`;
    document.getElementById('alerts-pagination').innerHTML = '';
    return;
  }

  tbody.innerHTML = alerts.map((a, i) => {
    const isResolved = !!a.resolved_at;
    const isAcked    = !!a.acknowledged;
    const rowOpacity = (isResolved || isAcked) ? 'opacity:0.5;' : '';
    return `
      <tr class="${isResolved?'':(a.severity==='critical'?'state-critical':a.severity==='warning'?'state-warning':'state-info')}"
          style="${rowOpacity}animation:fadeInUp 0.2s ease forwards;animation-delay:${Math.min(i*0.03,0.3)}s"
          onclick="toggleAlertMessage(this, ${a.id})">
        <td>${severityBadge(a.severity)}</td>
        <td>
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
            <span style="font-weight:500;color:var(--text-primary)">${esc(trunc(a.resource_name||a.resource_id,28))}</span>
            ${typeBadge(a.resource_type)}
          </div>
          <div class="resource-id">${esc(trunc(a.resource_id,32))}</div>
        </td>
        <td><span style="color:var(--text-secondary);font-size:0.78rem">${esc(a.alert_type.replace(/_/g,' '))}</span></td>
        <td><span title="${esc(a.triggered_at)}" style="color:var(--text-secondary);font-size:0.78rem">${relativeTime(a.triggered_at)}</span></td>
        <td>${isResolved?`<span style="color:var(--success);font-size:0.75rem;font-weight:600">✓ resolved</span>`:isAcked?`<span style="color:var(--text-dim);font-size:0.75rem">acknowledged</span>`:`<span style="color:var(--critical);font-size:0.75rem;font-weight:600">● open</span>`}</td>
        <td>${!isResolved&&!isAcked?`<button class="ack-btn" onclick="acknowledgeAlert(event,${a.id},this)">✓ Ack</button>`:'<span style="color:var(--text-dim)">—</span>'}</td>
      </tr>
      <tr class="alert-message-row" id="msg-${a.id}" style="display:none">
        <td colspan="6"><div class="alert-message-text">${esc(a.message)}</div></td>
      </tr>`;
  }).join('');

  const pages = meta.pages || 1;
  const pg = document.getElementById('alerts-pagination');
  if (pages <= 1) { pg.innerHTML = ''; return; }
  let btns = `<button class="page-btn" ${currentPage===1?'disabled':''} onclick="goPage(${currentPage-1})">‹</button>`;
  for (let p=1; p<=pages; p++) {
    if (p===1||p===pages||Math.abs(p-currentPage)<=1) btns+=`<button class="page-btn${p===currentPage?' active':''}" onclick="goPage(${p})">${p}</button>`;
    else if (Math.abs(p-currentPage)===2) btns+=`<span style="color:var(--text-dim);padding:0 4px">…</span>`;
  }
  btns += `<button class="page-btn" ${currentPage===pages?'disabled':''} onclick="goPage(${currentPage+1})">›</button>`;
  pg.innerHTML = btns;
}

function toggleAlertMessage(row, alertId) {
  const msgRow = document.getElementById(`msg-${alertId}`);
  if (msgRow) msgRow.style.display = msgRow.style.display === 'none' ? '' : 'none';
}

async function acknowledgeAlert(event, alertId, btn) {
  event.stopPropagation();
  btn.disabled = true; btn.textContent = '...';
  const result = await apiPost(`/api/alerts/${alertId}/acknowledge`);
  if (result && result.success) {
    const row = btn.closest('tr');
    if (row) {
      row.style.opacity = '0.5';
      btn.classList.add('acknowledged'); btn.textContent = '✓ Done';
      const statusTd = row.querySelectorAll('td')[4];
      if (statusTd) statusTd.innerHTML = `<span style="color:var(--text-dim);font-size:0.75rem">acknowledged</span>`;
    }
    loadSidebarData();
  } else {
    btn.disabled = false; btn.textContent = '✓ Ack';
    btn.style.borderColor = 'var(--critical)'; btn.style.color = 'var(--critical)';
    setTimeout(() => { btn.style.borderColor = ''; btn.style.color = ''; }, 2000);
  }
}

function goPage(p) {
  currentPage = Math.max(1, Math.min(p, Math.ceil(totalAlerts/PAGE_SIZE)));
  fetchAlerts();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

document.addEventListener('DOMContentLoaded', loadAlerts);