from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.analysis import analyze_purchase_history
from app.data import load_supplier
from app.mockdesk_client import MockDeskGateway, MockDeskUnavailableError
from app.models import (
    ActionPreview,
    AnalysisResponse,
    Citation,
    PurchaseRequest,
    TicketResult,
)
from app.narrator import explain_decision
from app.policy_engine import PolicyEngine
from app.retrieval import PolicyRepository
from app.security import authorize, matched_injection_rule
from app.store import SQLiteStore


class ProcurementService:
    def __init__(
        self,
        *,
        store: SQLiteStore,
        mockdesk_gateway: MockDeskGateway,
        policy_repository: PolicyRepository,
        policy_engine: PolicyEngine,
        suppliers_path: Path,
        purchase_history_path: Path,
    ) -> None:
        self.store = store
        self.mockdesk_gateway = mockdesk_gateway
        self.policy_repository = policy_repository
        self.policy_engine = policy_engine
        self.suppliers_path = suppliers_path
        self.purchase_history_path = purchase_history_path

    @classmethod
    def from_project_data(
        cls,
        *,
        store: SQLiteStore,
        mockdesk_gateway: MockDeskGateway,
        project_root: Path,
    ) -> ProcurementService:
        return cls(
            store=store,
            mockdesk_gateway=mockdesk_gateway,
            policy_repository=PolicyRepository(project_root / "data" / "documents.json"),
            policy_engine=PolicyEngine.from_yaml(project_root / "data" / "policy_rules.yaml"),
            suppliers_path=project_root / "data" / "suppliers.csv",
            purchase_history_path=project_root / "data" / "purchase_history.csv",
        )

    def analyze(self, request: PurchaseRequest, *, role: str, user: str) -> AnalysisResponse:
        authorize(role, "analyze_request")
        trace_id = f"trace-{uuid4().hex[:12]}"
        self.store.add_audit(
            event_type="REQUEST_RECEIVED",
            actor=user,
            request_id=request.request_id,
            trace_id=trace_id,
            details={"amount_try": str(request.amount_try)},
        )
        self._quarantine_untrusted_attachments(request, trace_id)
        supplier = load_supplier(self.suppliers_path, request.supplier_name)
        analysis = analyze_purchase_history(request, self.purchase_history_path)
        policy = self.policy_repository.current_policy(
            "PROCUREMENT_POLICY", request.request_date, role
        )
        compliance_policy = self.policy_repository.current_policy(
            "SUPPLIER_COMPLIANCE_POLICY", request.request_date, role
        )
        decision = self.policy_engine.evaluate(request, analysis, supplier)
        approval = self.store.create_approval(
            request_id=request.request_id,
            action_type="CREATE_PROCUREMENT_EXCEPTION_TICKET",
            requested_by=user,
        )
        citations = [
            Citation(
                document_id=document.document_id,
                version=document.version,
                title=document.title,
                section_id=section_id,
                section_title=document.section(section_id).title,
                status=document.status,
                effective_from=document.effective_from,
            )
            for document, section_id in (
                (policy, "4.2"),
                (policy, "4.3"),
                (compliance_policy, "3.1"),
            )
        ]
        response = AnalysisResponse(
            request=request,
            supplier=supplier,
            analysis=analysis,
            decision=decision,
            citations=citations,
            approval=approval,
            explanation=explain_decision(decision, analysis),
            trace_id=trace_id,
        )
        self.store.save_case(
            approval.approval_id,
            response.model_dump(mode="json"),
        )
        for event_type, details in (
            ("POLICY_RETRIEVED", {"document_id": policy.document_id, "version": policy.version}),
            ("PURCHASE_ANALYZED", response.analysis.model_dump(mode="json")),
            ("POLICY_EVALUATED", response.decision.model_dump(mode="json")),
            ("APPROVAL_REQUESTED", {"approval_id": approval.approval_id}),
        ):
            self.store.add_audit(
                event_type=event_type,
                actor="system",
                request_id=request.request_id,
                approval_id=approval.approval_id,
                trace_id=trace_id,
                details=details,
            )
        return response

    def _quarantine_untrusted_attachments(self, request: PurchaseRequest, trace_id: str) -> None:
        attachments = self.policy_repository.untrusted_attachments(request.supplier_name)
        for document_id, content in attachments:
            rule_id = matched_injection_rule(content)
            if rule_id is None:
                continue
            self.store.add_audit(
                event_type="SECURITY_CONTENT_QUARANTINED",
                actor="system",
                request_id=request.request_id,
                trace_id=trace_id,
                details={"document_id": document_id, "rule_id": rule_id},
            )

    def approve(self, approval_id: str, *, role: str, user: str):
        record = self.store.approve(approval_id, approved_by=user, approver_role=role)
        case = self.store.load_case(approval_id)
        self.store.add_audit(
            event_type="APPROVAL_GRANTED",
            actor=user,
            request_id=record.request_id,
            approval_id=approval_id,
            trace_id=case["trace_id"],
            details={"status": record.status},
        )
        return record

    def action_preview(self, approval_id: str, *, role: str) -> ActionPreview:
        authorize(role, "view_action_preview")
        approval = self.store.get_approval(approval_id)
        case = self.store.load_case(approval_id)
        payload, idempotency_key = self._build_action(approval.request_id, case)
        return ActionPreview(
            approval_id=approval.approval_id,
            target_system="MOCKDESK",
            operation=approval.action_type,
            idempotency_key=idempotency_key,
            payload=payload,
            required_role="finance_approver",
        )

    @staticmethod
    def _build_action(request_id: str, case: dict) -> tuple[dict[str, object], str]:
        payload: dict[str, object] = {
            "request_id": request_id,
            "summary": "Procurement Exception Review",
            "decision_status": case["decision"]["decision_status"],
            "reasons": case["decision"]["blocking_reasons"],
        }
        return payload, f"{request_id}-PROCUREMENT-REVIEW"

    def reject(self, approval_id: str, *, role: str, user: str):
        record = self.store.reject(approval_id, approver_role=role)
        case = self.store.load_case(approval_id)
        self.store.add_audit(
            event_type="APPROVAL_REJECTED",
            actor=user,
            request_id=record.request_id,
            approval_id=approval_id,
            trace_id=case["trace_id"],
            details={"status": record.status},
        )
        return record

    def execute(self, approval_id: str, *, role: str, user: str) -> TicketResult:
        authorize(role, "execute_tool_action")
        approval = self.store.require_approved(approval_id)
        case = self.store.load_case(approval_id)
        request_id = approval.request_id
        payload, idempotency_key = self._build_action(request_id, case)
        try:
            result = self.mockdesk_gateway.create_ticket(
                payload,
                idempotency_key=idempotency_key,
            )
        except MockDeskUnavailableError as exc:
            self.store.add_audit(
                event_type="TOOL_EXECUTION_FAILED",
                actor=user,
                request_id=request_id,
                approval_id=approval_id,
                trace_id=case["trace_id"],
                details={"error": str(exc), "idempotency_key": idempotency_key},
            )
            raise
        self.store.add_audit(
            event_type="TOOL_EXECUTED",
            actor=user,
            request_id=request_id,
            approval_id=approval_id,
            trace_id=case["trace_id"],
            details=result.model_dump(mode="json"),
        )
        return result
