from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.mockdesk_client import InProcessMockDeskGateway
from app.service import ProcurementService
from app.store import SQLiteStore
from mockdesk.store import MockDeskStore

ROOT = Path(__file__).resolve().parents[1]


def _client(tmp_path: Path) -> TestClient:
    service = ProcurementService.from_project_data(
        store=SQLiteStore(tmp_path / "valuebridge.db"),
        mockdesk_gateway=InProcessMockDeskGateway(MockDeskStore(tmp_path / "mockdesk.db")),
        project_root=ROOT,
    )
    return TestClient(create_app(service=service))


def test_home_exposes_the_interactive_hero_flow(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/")

    assert response.status_code == 200
    assert "Talebi Analiz Et" in response.text
    assert "İnsan Onayını Ver" in response.text
    assert "/static/app.js" in response.text


def test_home_ships_a_region_for_every_workflow_state(tmp_path: Path) -> None:
    html = _client(tmp_path).get("/").text

    for element_id in (
        "intake-text",
        "intake-button",
        "intake-notice",
        "intake-error",
        "analysis-loading",
        "analysis-error",
        "security-notice",
        "llm-narrative",
        "approval-status",
        "execution-success",
        "duplicate-notice",
        "action-error",
        "audit-events",
        "qa-input",
        "qa-button",
        "qa-results",
        "qa-answer",
        "qa-mode",
    ):
        assert f'id="{element_id}"' in html, element_id


def test_home_labels_pending_failure_duplicate_and_quarantine_states(tmp_path: Path) -> None:
    html = _client(tmp_path).get("/").text

    assert "ONAY BEKLİYOR" in html
    assert "Analiz başarısız" in html
    assert "ALREADY_PROCESSED" in html
    assert "SECURITY_CONTENT_QUARANTINED" in html


def test_state_regions_are_announced_and_hidden_until_used(tmp_path: Path) -> None:
    html = _client(tmp_path).get("/").text

    banners = [line for line in html.splitlines() if 'class="state-banner' in line]
    assert len(banners) == 10, banners
    for line in banners:
        assert 'role="status"' in line or 'role="alert"' in line, line
        assert "hidden" in line, line
    assert 'aria-live="polite"' in html


def test_intake_fills_the_form_without_starting_the_analysis(tmp_path: Path) -> None:
    script = _client(tmp_path).get("/static/app.js").text
    handler = script.split("intakeButton.addEventListener", 1)[1].split("\n});", 1)[0]

    assert "/api/v1/requests/intake" in handler
    assert "showBanner('#intake-error'" in handler
    assert "body.missing_fields" in handler
    assert "body.injection_rule_id" in handler
    assert "applyDraft(body.draft);" in handler
    assert "/api/v1/requests/analyze" not in handler


def test_narrative_is_rendered_as_text_only_when_the_model_answered(tmp_path: Path) -> None:
    script = _client(tmp_path).get("/static/app.js").text
    html = _client(tmp_path).get("/").text

    assert "showBanner('#llm-narrative', body.llm_narrative)" in script
    assert "hideBanner('#llm-narrative')" in script
    assert 'id="llm-narrative-text"' in html
    assert "Karar deterministik motordan gelir" in html


def test_security_notice_is_scoped_to_the_analysed_request(tmp_path: Path) -> None:
    script = _client(tmp_path).get("/static/app.js").text

    assert "analysisTraceId = body.trace_id" in script
    assert "item.trace_id === analysisTraceId" in script


def test_failed_analysis_clears_the_stale_decision_and_approval(tmp_path: Path) -> None:
    script = _client(tmp_path).get("/static/app.js").text
    submit_handler = script.split("form.addEventListener", 1)[1].split("async function", 1)[0]
    reset = script.split("function clearAnalysisResult() {", 1)[-1].split("\n}", 1)[0]

    assert submit_handler.count("clearAnalysisResult();") == 2, submit_handler
    assert "approvalId = null" in reset
    assert "analysisTraceId = null" in reset
    assert "approveButton.disabled = true" in reset
    assert "rejectButton.disabled = true" in reset
    assert "executeButton.disabled = true" in reset
    assert "analysisCard.classList.add('hidden')" in reset
    assert "approvalCard.classList.add('hidden')" in reset


def test_approval_buttons_wait_for_a_successful_action_preview(tmp_path: Path) -> None:
    script = _client(tmp_path).get("/static/app.js").text
    submit_handler = script.split("form.addEventListener", 1)[1].split("async function", 1)[0]
    preview = script.split("async function renderActionPreview() {", 1)[-1].split("\n}", 1)[0]

    assert "approveButton.disabled = false" not in submit_handler, submit_handler
    assert "rejectButton.disabled = false" not in submit_handler, submit_handler
    assert "const previewLoaded = await renderActionPreview();" in submit_handler
    assert "applyApprovalState(body.approval, previewLoaded);" in submit_handler
    assert submit_handler.index("await renderActionPreview()") < submit_handler.index(
        "applyApprovalState(body.approval, previewLoaded);"
    )
    assert "catch (previewError)" in preview
    assert "showBanner('#action-error'" in preview
    assert preview.count("return false;") == 2, preview
    assert "return true;" in preview


def test_approval_controls_follow_the_approval_state(tmp_path: Path) -> None:
    script = _client(tmp_path).get("/static/app.js").text
    state_fn = script.split("function applyApprovalState(", 1)[-1].split("\n}", 1)[0]

    assert "function applyApprovalState(" in script
    assert "approval.status === 'PENDING'" in state_fn
    assert "approval.status === 'APPROVED'" in state_fn
    assert "approveButton.disabled = !(isPending && previewLoaded);" in state_fn
    assert "rejectButton.disabled = !(isPending && previewLoaded);" in state_fn
    assert "executeButton.disabled = !isApproved;" in state_fn


def test_audit_drawer_uses_safe_dom_nodes_for_trace_and_json(tmp_path: Path) -> None:
    script = _client(tmp_path).get("/static/app.js").text

    assert "createElement('details'" in script
    assert "createElement('summary'" in script
    assert "Trace ID" in script
    assert "item.trace_id" in script
    assert "JSON.stringify(item.details" in script
    assert ".innerHTML" not in script


def test_stylesheet_ships_keyboard_focus_styles(tmp_path: Path) -> None:
    stylesheet = _client(tmp_path).get("/static/app.css").text

    assert ":focus-visible" in stylesheet
    assert ".state-banner" in stylesheet


def test_policy_question_card_posts_the_form_date_and_renders_text_only(tmp_path: Path) -> None:
    script = _client(tmp_path).get("/static/app.js").text
    html = _client(tmp_path).get("/").text
    handler = script.split("qaButton.addEventListener", 1)[1].split("\n});", 1)[0]

    assert "Politika Soru-Cevap" in html
    assert "Politikaya Sor" in html
    assert 'id="qa-answer-text"' in html
    assert "/api/v1/policies/ask" in handler
    assert "headers('procurement_specialist', 'procurement_user')" in handler
    assert "form.elements.namedItem('request_date')" in handler
    assert "'2026-08-18'" in handler
    assert "showBanner('#qa-answer', body.answer)" in handler
    assert "hideBanner('#qa-answer')" in handler
    assert "body.retrieval_mode" in handler


def test_intake_clears_fields_the_assistant_could_not_extract(tmp_path: Path) -> None:
    script = _client(tmp_path).get("/static/app.js").text
    apply_draft = script.split("function applyDraft(", 1)[1].split("\n}", 1)[0]
    handler = script.split("intakeButton.addEventListener", 1)[1].split("\n});", 1)[0]

    assert "if (value === null) return;" not in apply_draft
    assert "field.value = value === null ? '' : String(value);" in apply_draft
    assert "clearAnalysisResult();" in handler
    assert "statusBadge.textContent = 'ANALİZE HAZIR';" in handler
