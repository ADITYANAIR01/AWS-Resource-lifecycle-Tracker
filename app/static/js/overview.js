'use strict';

const TYPE_COLORS = {
  ec2:'#60a5fa', rds:'#a78bfa', s3:'#f472b6',
  ebs_volume:'#34d399', ebs_snapshot:'#6ee7b7',
  elastic_ip:'#fb923c', security_group:'#94a3b8',
  iam_user:'#fbbf24', cloudwatch_alarm:'#f87171', rds_snapshot:'#c084fc',
};

const TYPE_LABELS = {
  ec2:'EC2 Instances', rds:'RDS Instances', s3:'S3 Buckets',
  ebs_volume:'EBS Volumes', ebs_snapshot:'EBS Snapshots',
  elastic_ip:'Elastic IPs', security_group:'Security Groups',
  iam_user:'IAM Users', cloudwatch_alarm:'CloudWatch Alarms', rds_snapshot:'RDS Snapshots',
};

async function loadOverview() {
  const data = await apiFetch('/api/overview');
  if (!data) return;

  animateCount(document.getElementById('stat-resources'), data.total_resources || 0);
  document.getElementById('stat-resources-sub').textContent =
    `${(data.resources_by_type || []).length} resource types`;

  const alertCount = data.total_alerts || 0;
  animateCount(document.getElementById('stat-alerts'), alertCount);
  if (alertCount > 0) {
    document.getElementById('card-alerts').style.borderColor = 'rgba(255,68,68,0.3)';
    document.getElementById('stat-alerts').style.color = 'var(--critical)';
  }
  const sev = data.alerts_by_severity || {};
  const parts = [];
  if (sev.critical) parts.push(`${sev.critical} critical`);
  if (sev.warning)  parts.push(`${sev.warning} warning`);
  if (sev.info)     parts.push(`${sev.info} info`);
  document.getElementById('stat-alerts-sub').textContent = parts.join(' · ') || 'All clear';

  const cost = parseFloat(data.total_cost_usd || 0);
  document.getElementById('stat-cost').textContent = cost > 0 ? `$${cost.toFixed(2)}` : '$0.00';

  const lr = data.last_run;
  if (lr) {
    const statusMap = {
      success:{ label:'✓ SUCCESS', color:'var(--success)' },
      partial_failure:{ label:'⚠ PARTIAL', color:'var(--warning)' },
      failed:{ label:'✗ FAILED', color:'var(--critical)' },
      running:{ label:'⟳ RUNNING', color:'var(--info)' },
    };
    const s = statusMap[lr.status] || { label: lr.status, color:'var(--text-secondary)' };
    document.getElementById('stat-poll-status').textContent = s.label;
    document.getElementById('stat-poll-status').style.color = s.color;
    document.getElementById('stat-poll-sub').textContent =
      `run #${lr.id} · ${relativeTime(lr.completed_at || lr.started_at)}`;
  }

  const bars = document.getElementById('resource-bars');
  const types = data.resources_by_type || [];
  const maxCount = Math.max(...types.map(t => t.count), 1);

  bars.innerHTML = types.map((t, i) => {
    const color = TYPE_COLORS[t.resource_type] || '#7a9bc4';
    const label = TYPE_LABELS[t.resource_type] || t.resource_type;
    const pct = Math.round((t.count / maxCount) * 100);
    return `
      <div class="resource-bar-row" onclick="window.location='/resources?type=${t.resource_type}'"
           style="animation:fadeInUp 0.3s ease forwards;animation-delay:${i*0.05}s">
        <span class="bar-label" style="color:${color}">${label}</span>
        <div class="bar-track">
          <div class="bar-fill" data-pct="${pct}"
               style="background:linear-gradient(90deg,${color},${color}88)"></div>
        </div>
        <span class="bar-count">${t.count}</span>
      </div>`;
  }).join('');

  requestAnimationFrame(() => {
    document.querySelectorAll('.bar-fill').forEach(el => { el.style.width = el.dataset.pct + '%'; });
  });

  const alertData = await apiFetch('/api/alerts?status=active&page=1');
  if (!alertData) return;

  const alerts = alertData.alerts || [];
  const alertSummary = document.getElementById('alert-summary');
  const viewAll = document.getElementById('view-all-alerts');

  if (alerts.length === 0) {
    alertSummary.innerHTML = `<div class="all-clear"><span style="font-size:1.5rem">✓</span><span>All clear — no active alerts</span></div>`;
  } else {
    alertSummary.innerHTML = alerts.slice(0,5).map(a => `
      <a href="/alerts" class="alert-summary-item ${a.severity}" style="margin-bottom:8px;display:flex">
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:3px">
            ${severityBadge(a.severity)}
            <span style="font-weight:600;color:var(--text-primary);font-size:0.8rem">${esc(trunc(a.resource_name||a.resource_id,24))}</span>
            ${typeBadge(a.resource_type)}
          </div>
          <div style="font-size:0.75rem;color:var(--text-dim)">${esc(trunc(a.alert_type.replace(/_/g,' '),40))}</div>
        </div>
        <div style="font-size:0.7rem;color:var(--text-dim);white-space:nowrap;padding-left:8px">${relativeTime(a.triggered_at)}</div>
      </a>`).join('');
    if (alertData.total > 5) viewAll.style.display = '';
  }
}

document.addEventListener('DOMContentLoaded', loadOverview);