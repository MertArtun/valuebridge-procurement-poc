const form = document.querySelector('#request-form');
const analysisCard = document.querySelector('#analysis-card');
const approvalCard = document.querySelector('#approval-card');
const statusBadge = document.querySelector('#workflow-status');
const approveButton = document.querySelector('#approve-button');
const executeButton = document.querySelector('#execute-button');
const auditButton = document.querySelector('#audit-button');
let approvalId = null;

const headers = (role, user) => ({
  'Content-Type': 'application/json',
  'X-Demo-Role': role,
  'X-Demo-User': user,
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  statusBadge.textContent = 'ANALİZ EDİLİYOR';
  const data = Object.fromEntries(new FormData(form).entries());
  data.received_quotes = Number(data.received_quotes);
  data.offered_lead_time_days = Number(data.offered_lead_time_days);

  const response = await fetch('/api/v1/requests/analyze', {
    method: 'POST',
    headers: headers('procurement_specialist', 'procurement_user'),
    body: JSON.stringify(data),
  });
  const body = await response.json();
  if (!response.ok) {
    statusBadge.textContent = 'HATA';
    document.querySelector('#explanation').textContent = JSON.stringify(body, null, 2);
    analysisCard.classList.remove('hidden');
    return;
  }

  approvalId = body.approval.approval_id;
  statusBadge.textContent = body.decision.decision_status;
  document.querySelector('#analysis-summary').innerHTML = [
    ['Talep', `${Number(body.request.amount_try).toLocaleString('tr-TR')} TL`],
    ['Geçmiş Medyan', `${Number(body.analysis.historical_median_try).toLocaleString('tr-TR')} TL`],
    ['Fiyat Sapması', `%${body.analysis.display_variance_percent}`],
    ['Sertifika', body.decision.certificate_status],
  ].map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`).join('');
  document.querySelector('#decision-reasons').innerHTML = body.decision.blocking_reasons
    .map((reason) => `<li>${reason}</li>`).join('');
  document.querySelector('#citations').innerHTML = body.citations.map((citation) => `
    <article class="citation">
      <strong>${citation.title} v${citation.version}</strong>
      <span>Bölüm ${citation.section_id} — ${citation.section_title}</span>
      <small>${citation.status} · ${citation.effective_from}</small>
    </article>`).join('');
  document.querySelector('#explanation').textContent = body.explanation;
  analysisCard.classList.remove('hidden');
  approvalCard.classList.remove('hidden');
  approveButton.disabled = false;
  executeButton.disabled = true;
  await refreshAudit();
});

approveButton.addEventListener('click', async () => {
  const response = await fetch(`/api/v1/approvals/${approvalId}/approve`, {
    method: 'POST',
    headers: headers('finance_approver', 'finance_user'),
  });
  const body = await response.json();
  document.querySelector('#action-result').textContent = JSON.stringify(body, null, 2);
  if (response.ok) {
    approveButton.disabled = true;
    executeButton.disabled = false;
  }
  await refreshAudit();
});

executeButton.addEventListener('click', async () => {
  const response = await fetch(`/api/v1/tool-actions/${approvalId}/execute`, {
    method: 'POST',
    headers: headers('procurement_specialist', 'procurement_user'),
  });
  const body = await response.json();
  document.querySelector('#action-result').textContent = JSON.stringify(body, null, 2);
  await refreshAudit();
});

auditButton.addEventListener('click', refreshAudit);

async function refreshAudit() {
  const response = await fetch('/api/v1/audit/events', {
    headers: headers('solution_engineer', 'solution_engineer'),
  });
  const events = await response.json();
  const container = document.querySelector('#audit-events');
  if (!response.ok || !Array.isArray(events)) {
    container.innerHTML = `<pre>${JSON.stringify(events, null, 2)}</pre>`;
    return;
  }
  container.innerHTML = events.length ? events.map((item) => `
    <div class="audit-event">
      <code>${item.event_type}</code>
      <span>${item.actor}</span>
      <small>${item.trace_id}</small>
    </div>`).join('') : '<p>Henüz olay yok.</p>';
}
