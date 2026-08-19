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
  SUPERSEDED: 'GEÇERSİZ KILINDI',
};

function createElement(tag, options = {}) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = String(options.text);
  return node;
}

function replaceChildren(selector, ...children) {
  document.querySelector(selector).replaceChildren(...children);
}

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

function renderMetrics(items) {
  return items.map(([label, value]) => {
    const wrapper = createElement('div', { className: 'metric' });
    wrapper.append(
      createElement('span', { text: label }),
      createElement('strong', { text: value }),
    );
    return wrapper;
  });
}

function renderAnalysis(body) {
  replaceChildren(
    '#analysis-summary',
    ...renderMetrics([
      ['Talep', `${Number(body.request.amount_try).toLocaleString('tr-TR')} TL`],
      ['Geçmiş Medyan', `${Number(body.analysis.historical_median_try).toLocaleString('tr-TR')} TL`],
      ['Fiyat Sapması', `%${body.analysis.display_variance_percent}`],
      ['Sertifika', body.decision.certificate_status],
    ]),
  );

  const reasons = body.decision.blocking_reasons.map((reason) =>
    createElement('li', { text: reason }));
  replaceChildren('#decision-reasons', ...reasons);

  const citations = body.citations.map((citation) => {
    const article = createElement('article', { className: 'citation' });
    article.append(
      createElement('strong', { text: `${citation.title} v${citation.version}` }),
      createElement('span', {
        text: `Bölüm ${citation.section_id} — ${citation.section_title}`,
      }),
      createElement('small', {
        text: `${citation.status} · ${citation.effective_from}`,
      }),
    );
    return article;
  });
  replaceChildren('#citations', ...citations);
  document.querySelector('#explanation').textContent = body.explanation;
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
    await refreshAudit();
    return;
  }

  approvalId = body.approval ? body.approval.approval_id : null;
  analysisTraceId = body.trace_id;
  hideBanner('#security-notice');
  hideBanner('#execution-success');
  hideBanner('#duplicate-notice');
  hideBanner('#action-error');
  document.querySelector('#action-result').textContent = '';
  statusBadge.textContent = body.decision.decision_status;
  renderAnalysis(body);
  analysisCard.classList.remove('hidden');

  if (body.approval) {
    approvalStatus.textContent = APPROVAL_LABELS[body.approval.status] || body.approval.status;
    approvalCard.classList.remove('hidden');
    approveButton.disabled = true;
    rejectButton.disabled = true;
    executeButton.disabled = true;
    const previewLoaded = await renderActionPreview();
    applyApprovalState(body.approval, previewLoaded);
  } else {
    approvalCard.classList.add('hidden');
  }
  await refreshAudit();
});

function applyApprovalState(approval, previewLoaded) {
  const isPending = approval.status === 'PENDING';
  const isApproved = approval.status === 'APPROVED';
  approveButton.disabled = !(isPending && previewLoaded);
  rejectButton.disabled = !(isPending && previewLoaded);
  executeButton.disabled = !isApproved;
}

async function renderActionPreview() {
  const container = document.querySelector('#action-preview');
  let response;
  let preview;
  try {
    response = await fetch(`/api/v1/approvals/${approvalId}/action-preview`, {
      headers: headers('procurement_specialist', 'procurement_user'),
    });
    preview = await response.json();
  } catch (previewError) {
    container.replaceChildren(createElement('p', { text: 'Aksiyon önizlemesi alınamadı.' }));
    showBanner('#action-error', `Aksiyon önizlemesi alınamadı: ${previewError.message}`);
    return false;
  }
  if (!response.ok) {
    const pre = createElement('pre', { text: JSON.stringify(preview, null, 2) });
    container.replaceChildren(pre);
    showBanner('#action-error', errorMessage(preview));
    return false;
  }

  const title = createElement('h3', { text: 'Gönderilecek Aksiyon' });
  const metrics = renderMetrics([
    ['Hedef Sistem', preview.target_system],
    ['Operasyon', preview.operation],
    ['Idempotency Anahtarı', preview.idempotency_key],
    ['Gereken Onay Rolü', preview.required_role],
  ]);
  const payload = createElement('pre', { text: JSON.stringify(preview.payload, null, 2) });
  container.replaceChildren(title, ...metrics, payload);
  return true;
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

const metricsButton = document.querySelector('#metrics-button');

async function refreshMetrics() {
  const container = document.querySelector('#metrics-summary');
  let response;
  let summary;
  try {
    response = await fetch('/api/v1/metrics/summary', {
      headers: headers('solution_engineer', 'solution_engineer'),
    });
    summary = await response.json();
  } catch (metricsError) {
    container.replaceChildren(createElement('p', { text: 'Metrikler alınamadı.' }));
    return;
  }
  if (!response.ok) {
    container.replaceChildren(createElement('pre', { text: JSON.stringify(summary, null, 2) }));
    return;
  }
  const cycle = summary.median_cycle_time_seconds;
  container.replaceChildren(
    ...renderMetrics([
      ['Toplam Analiz', summary.analyses_total],
      ['Koşullu İnceleme', summary.decisions.CONDITIONAL_REVIEW],
      ['Reddedilen Talep', summary.decisions.REJECTED],
      ['Açılan Kayıt', summary.tickets_created],
      ['Önlenen Duplicate', summary.duplicates_prevented],
      ['Karantina', summary.quarantined_attachments],
      ['Engellenen Deneme', summary.denied_or_blocked_actions],
      ['Medyan Çevrim (sn)', cycle === null ? '—' : cycle],
    ]),
  );
}

metricsButton.addEventListener('click', refreshMetrics);

function auditEventNode(item) {
  const details = createElement('details', { className: 'audit-event' });
  const summary = createElement('summary');
  summary.append(
    createElement('code', { text: item.event_type }),
    createElement('span', { text: item.actor }),
    createElement('small', { text: item.timestamp }),
  );
  const body = createElement('div', { className: 'audit-detail' });
  const trace = createElement('p', { className: 'audit-trace' });
  trace.append(
    document.createTextNode('Trace ID: '),
    createElement('code', { text: item.trace_id }),
  );
  body.append(trace, createElement('pre', { text: JSON.stringify(item.details, null, 2) }));
  details.append(summary, body);
  return details;
}

async function refreshAudit() {
  const response = await fetch('/api/v1/audit/events', {
    headers: headers('solution_engineer', 'solution_engineer'),
  });
  const events = await response.json();
  const container = document.querySelector('#audit-events');
  if (!response.ok || !Array.isArray(events)) {
    container.replaceChildren(createElement('pre', { text: JSON.stringify(events, null, 2) }));
    return;
  }
  if (events.length) {
    container.replaceChildren(...events.map(auditEventNode));
  } else {
    container.replaceChildren(createElement('p', { text: 'Henüz olay yok.' }));
  }
  renderSecurityNotice(events);
  await refreshMetrics();
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
