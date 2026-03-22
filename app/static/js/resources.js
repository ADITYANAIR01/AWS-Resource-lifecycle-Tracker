'use strict';

let allResources = [];
let filteredResources = [];
let currentPage = 1;
const PAGE_SIZE = 50;
let sortKey = 'created_at';
let sortDir = -1;

function getUrlParam(key) {
  return new URLSearchParams(window.location.search).get(key) || '';
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
    if (state  && r.state !== state)          return false;
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
            `<span class="tag-pill"><span class="tag-key">${esc(k)}</span><span style="color:var(--text-dim)">:</span><span class="tag-val">${esc(trunc(v,16))}</span></span>`
          ).join(' ')
        : '<span style="color:var(--text-dim);font-size:0.7rem">—</span>';

      return `
        <tr class="${stateRowClass(r.state)}"
            style="animation:fadeInUp 0.2s ease forwards;animation-delay:${Math.min(i*0.02,0.3)}s;opacity:0"
            onclick="window.location='/resources/${esc(r.resource_type)}/${esc(r.resource_id)}'">
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
          <td><span style="color:var(--text-dim);font-size:0.8rem">→</span></td>
        </tr>`;
    }).join('');
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

document.addEventListener('DOMContentLoaded', loadResources);