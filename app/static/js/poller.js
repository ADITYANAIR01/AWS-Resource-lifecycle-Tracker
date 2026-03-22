'use strict';

async function loadPollerStatus() {
  const data = await apiFetch('/api/poller');
  if (!data) return;

  const runs = data.runs || [];
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
      <tr class="${rowClass}" style="animation:fadeInUp 0.2s ease forwards;animation-delay:${Math.min(i*0.03,0.4)}s;opacity:0"
          onclick="${hasError?`toggleErrorLog(${run.id})`:''}">
        <td><span class="mono" style="color:var(--accent)">#${run.id}</span></td>
        <td><span title="${esc(run.started_at)}" style="color:var(--text-secondary);font-size:0.8rem">${formatDate(run.started_at)}</span></td>
        <td><span class="mono" style="font-size:0.78rem;color:var(--text-secondary)">${run.duration_seconds!=null?run.duration_seconds+'s':'—'}</span></td>
        <td><span class="mono" style="color:var(--text-primary)">${run.resources_found??0}</span></td>
        <td><span class="mono" style="color:${run.resources_new>0?'var(--success)':'var(--text-dim)'}">${run.resources_new??0}</span></td>
        <td><span class="mono" style="color:var(--text-secondary)">${run.resources_updated??0}</span></td>
        <td><span class="mono" style="color:${run.resources_deleted>0?'var(--warning)':'var(--text-dim)'}">${run.resources_deleted??0}</span></td>
        <td><span class="mono" style="color:${run.alerts_triggered>0?'var(--warning)':'var(--text-dim)'}">${run.alerts_triggered??0}</span></td>
        <td><span class="run-status ${s.cls}">${s.icon} ${run.status}</span>${hasError?`<span style="font-size:0.7rem;color:var(--text-dim);margin-left:6px">▼</span>`:''}</td>
      </tr>
      ${hasError?`<tr id="err-${run.id}" style="display:none"><td colspan="9"><div style="padding:12px 16px"><div class="error-log">${esc(run.error_log)}</div></div></td></tr>`:''}`;
  }).join('');
}

function toggleErrorLog(runId) {
  const row = document.getElementById(`err-${runId}`);
  if (row) row.style.display = row.style.display === 'none' ? '' : 'none';
}

document.addEventListener('DOMContentLoaded', loadPollerStatus);