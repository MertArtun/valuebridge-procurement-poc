const form = document.querySelector('#request-form');
const analysisCard = document.querySelector('#analysis-card');
const approvalCard = document.querySelector('#approval-card');
const statusBadge = document.querySelector('#workflow-status');
const approveButton = document.querySelector('#approve-button');
const rejectButton = document.querySelector('#reject-button');
const executeButton = document.querySelector('#execute-button');
const auditButton = document.querySelector('#audit-button');
const approvalStatus = document.querySelector('#approval-status');
let approvalId = null;
let analysisTraceId = null;

const headers = (role, user) => ({
  'Content-Type': 'application/json',
  'X-Demo-Role': role,
  'X-Demo-User': user,
});

const APPROVAL_LABELS = {
  PENDING: 'ONAY BEKLİYOR',
  APPROVED: 'ONAYLANDI',
  REJECTED: 'REDDEDİLDİ',
  EXPIRED: 'SÜRESİ DOLDU',
};

const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[character]));

function showBanner(selector, message) {
  const banner = document.querySelector(selector);
  if (message !== undefined) {
    banner.querySelector('span').textContent = message;
  }
  banner.classList.remove('hidden');
}

function hideBanner(selector) {
  document.querySelector(selector).classList.add('hidden');
}

function clearAnalysisResult() {
  approvalId = null;
  analysisTraceId = null;
  analysisCard.classList.add('hidden');
  approvalCard.classList.add('hidden');
  approveButton.disabled = true;
  rejectButton.disabled = true;
  executeButton.disabled = true;
}

function errorMessage(body) {
  if (body && body.error) {
    return `${body.error.code}: ${body.error.message}`;
  }
  if (Array.isArray(body && body.detail)) {
    return body.detail.map((item) => `${item.loc.at(-1)}: ${item.msg}`).join(' · ');
  }
  if (body && body.detail) {
    return String(body.detail);
  }
  return 'Beklenmeyen hata.';
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  statusBadge.textContent = 'ANALİZ EDİLİYOR';
  hideBanner('#analysis-error');
  showBanner('#analysis-loading');
  const data = Object.fromEntries(new FormData(form).entries());
  data.received_quotes = Number(data.received_quotes);
  data.offered_lead_time_days = Number(data.offered_lead_time_days);

  let response;
  let body;
  try {
    response = await fetch('/api/v1/requests/analyze', {
      method: 'POST',
      headers: headers('procurement_specialist', 'procurement_user'),
      body: JSON.stringify(data),
    });
    body = await response.json();
  } catch (networkError) {
    hideBanner('#analysis-loading');
    clearAnalysisResult();
    statusBadge.textContent = 'HATA';
    showBanner('#analysis-error', `Sunucuya ulaşılamadı: ${networkError.message}`);
    return;
  }
  hideBanner('#analysis-loading');
  if (!response.ok) {
    clearAnalysisResult();
    statusBadge.textContent = 'HATA';
    showBanner('#analysis-error', errorMessage(body));
    return;
  }

  approvalId = body.approval.approval_id;
  analysisTraceId = body.trace_id;
  approvalStatus.textContent = APPROVAL_LABELS[body.approval.status] || body.approval.status;
  hideBanner('#security-notice');
  hideBanner('#execution-success');
  hideBanner('#duplicate-notice');
  hideBanner('#action-error');
  document.querySelector('#action-result').textContent = '';
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
  rejectButton.disabled = false;
  executeButton.disabled = true;
  await renderActionPreview();
  await refreshAudit();
});

async function renderActionPreview() {
  const container = document.querySelector('#action-preview');
  const response = await fetch(`/api/v1/approvals/${approvalId}/action-preview`, {
    headers: headers('procurement_specialist', 'procurement_user'),
  });
  const preview = await response.json();
  if (!response.ok) {
    container.innerHTML = `<pre>${JSON.stringify(preview, null, 2)}</pre>`;
    return;
  }
  container.innerHTML = `
    <h3>Gönderilecek Aksiyon</h3>
    <div class="metric"><span>Hedef Sistem</span><strong>${preview.target_system}</strong></div>
    <div class="metric"><span>Operasyon</span><strong>${preview.operation}</strong></div>
    <div class="metric"><span>Idempotency Anahtarı</span><strong>${preview.idempotency_key}</strong></div>
    <div class="metric"><span>Gereken Onay Rolü</span><strong>${preview.required_role}</strong></div>
    <pre>${JSON.stringify(preview.payload, null, 2)}</pre>`;
}

approveButton.addEventListener('click', async () => {
  const response = await fetch(`/api/v1/approvals/${approvalId}/approve`, {
    method: 'POST',
    headers: headers('finance_approver', 'finance_user'),
  });
  const body = await response.json();
  document.querySelector('#action-result').textContent = JSON.stringify(body, null, 2);
  if (response.ok) {
    hideBanner('#action-error');
    approvalStatus.textContent = APPROVAL_LABELS[body.status] || body.status;
    approveButton.disabled = true;
    rejectButton.disabled = true;
    executeButton.disabled = false;
  } else {
    showBanner('#action-error', errorMessage(body));
  }
  await refreshAudit();
});

rejectButton.addEventListener('click', async () => {
  const response = await fetch(`/api/v1/approvals/${approvalId}/reject`, {
    method: 'POST',
    headers: headers('finance_approver', 'finance_user'),
  });
  const body = await response.json();
  document.querySelector('#action-result').textContent = JSON.stringify(body, null, 2);
  if (response.ok) {
    hideBanner('#action-error');
    statusBadge.textContent = 'REDDEDİLDİ';
    approvalStatus.textContent = APPROVAL_LABELS[body.status] || body.status;
    approveButton.disabled = true;
    rejectButton.disabled = true;
    executeButton.disabled = true;
  } else {
    showBanner('#action-error', errorMessage(body));
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
  if (!response.ok) {
    hideBanner('#execution-success');
    hideBanner('#duplicate-notice');
    showBanner('#action-error', errorMessage(body));
  } else if (body.status === 'ALREADY_PROCESSED') {
    hideBanner('#action-error');
    hideBanner('#execution-success');
    showBanner(
      '#duplicate-notice',
      `Aynı idempotency anahtarı ikinci kayıt açmadı; mevcut kayıt ${body.ticket_id}.`,
    );
  } else {
    hideBanner('#action-error');
    hideBanner('#duplicate-notice');
    showBanner('#execution-success', `Kayıt ${body.ticket_id} · durum ${body.status}.`);
  }
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
    <details class="audit-event">
      <summary>
        <code>${escapeHtml(item.event_type)}</code>
        <span>${escapeHtml(item.actor)}</span>
        <small>${escapeHtml(item.timestamp)}</small>
      </summary>
      <div class="audit-detail">
        <p class="audit-trace">Trace ID: <code>${escapeHtml(item.trace_id)}</code></p>
        <pre>${escapeHtml(JSON.stringify(item.details, null, 2))}</pre>
      </div>
    </details>`).join('') : '<p>Henüz olay yok.</p>';
  renderSecurityNotice(events);
}

function renderSecurityNotice(events) {
  const quarantined = events.filter((item) => item.event_type === 'SECURITY_CONTENT_QUARANTINED'
    && item.trace_id === analysisTraceId);
  if (!quarantined.length) {
    hideBanner('#security-notice');
    return;
  }
  const summary = quarantined
    .map((item) => `${item.details.document_id} (${item.details.rule_id})`)
    .join(', ');
  showBanner(
    '#security-notice',
    `Tedarikçi eki karantinaya alındı ve karar dışında tutuldu: ${summary}.`,
  );
}
