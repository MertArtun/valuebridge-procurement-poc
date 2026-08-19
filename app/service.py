from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from app.analysis import analyze_purchase_history
from app.data import load_supplier
from app.errors import (
    ApplicablePolicyNotFoundError,
    ApprovalContextChangedError,
    ApprovalRequiredError,
    AuthorizationError,
    IdempotencyConflictError,
    InvalidApprovalStateError,
    ValueBridgeError,
)
from app.mockdesk_client import MockDeskGateway
from app.models import (
    ActionPreview,
    AnalysisResponse,
    ApprovalRecord,
    Citation,
    PolicyDecision,
    PolicyDocument,
    PurchaseRequest,
    TicketResult,
)
from app.narrator import explain_decision
from app.policy_engine import PolicyEngine
from app.retrieval import PolicyRepository
from app.security import authorize, matched_injection_rule
from app.store import SQLiteStore

_RULE_CITATIONS: dict[str, tuple[str, str]] = {
    "FINANCE_APPROVAL": ("PROCUREMENT_POLICY", "4.2"),
    "ALTERNATIVE_QUOTES": ("PROCUREMENT_POLICY", "4.3"),
    "SUPPLIER_CERTIFICATE": ("SUPPLIER_COMPLIANCE_POLICY", "3.1"),
}


_CONTEXT_KEYS = ("request", "supplier", "analysis", "decision", "citations")


def _case_fingerprint(context: dict[str, object]) -> str:
    canonical = json.dumps(
        context,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _decision_context(case: dict[str, object]) -> dict[str, object]:
    return {key: case[key] for key in _CONTEXT_KEYS}


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
        trace_id = f"trace-{uuid4().hex[:12]}"
        try:
            authorize(role, "analyze_request")
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
            policies = {
                "PROCUREMENT_POLICY": self.policy_repository.current_policy(
                    "PROCUREMENT_POLICY", request.request_date, role
                ),
                "SUPPLIER_COMPLIANCE_POLICY": self.policy_repository.current_policy(
                    "SUPPLIER_COMPLIANCE_POLICY", request.request_date, role
                ),
            }
            decision = self.policy_engine.evaluate(request, analysis, supplier)
            citations = self._build_citations(decision, policies)
            context = {
                "request": request.model_dump(mode="json"),
                "supplier": supplier.model_dump(mode="json"),
                "analysis": analysis.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
                "citations": [item.model_dump(mode="json") for item in citations],
            }
            claim = self.store.reconcile_approval(
                request_id=request.request_id,
                action_type="CREATE_PROCUREMENT_EXCEPTION_TICKET",
                requested_by=user,
                required_role="finance_approver",
                case_fingerprint=_case_fingerprint(context),
                approval_required=decision.decision_status == "CONDITIONAL_REVIEW",
            )
            approval = claim.approval
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
            if approval is not None and not claim.reused:
                # A reused approval keeps its original case snapshot: the human
                # approved (or will approve) exactly that context, and the
                # fingerprint match guarantees this analysis is identical.
                self.store.save_case(
                    approval.approval_id,
                    response.model_dump(mode="json"),
                )
            approval_id = approval.approval_id if approval else None
            retrieved = [
                {
                    "document_id": citation.document_id,
                    "version": citation.version,
                    "section_id": citation.section_id,
                }
                for citation in citations
            ]
            events: list[tuple[str, dict[str, object]]] = [
                ("POLICY_RETRIEVED", {"citations": retrieved}),
                ("PURCHASE_ANALYZED", response.analysis.model_dump(mode="json")),
                ("POLICY_EVALUATED", response.decision.model_dump(mode="json")),
            ]
            if approval is not None:
                events.append(
                    (
                        "APPROVAL_REUSED" if claim.reused else "APPROVAL_REQUESTED",
                        {"approval_id": approval.approval_id},
                    )
                )
            for event_type, details in events:
                self.store.add_audit(
                    event_type=event_type,
                    actor="system",
                    request_id=request.request_id,
                    approval_id=approval_id,
                    trace_id=trace_id,
                    details=details,
                )
            for record in claim.superseded:
                self.store.add_audit(
                    event_type="APPROVAL_SUPERSEDED",
                    actor="system",
                    request_id=request.request_id,
                    approval_id=record.approval_id,
                    trace_id=trace_id,
                    details={"superseded_by": approval_id},
                )
            return response
        except AuthorizationError as exc:
            exc.attach_trace(trace_id)
            self.store.add_audit(
                event_type="AUTHORIZATION_DENIED",
                actor=user[:64],
                request_id=request.request_id,
                trace_id=trace_id,
                details={"role": role[:64], "action": "analyze_request"},
            )
            raise
        except ValueBridgeError as exc:
            exc.attach_trace(trace_id)
            self.store.add_audit(
                event_type="ANALYSIS_FAILED",
                actor="system",
                request_id=request.request_id,
                trace_id=trace_id,
                details={"code": exc.code, "message": str(exc)},
            )
            raise

    @staticmethod
    def _build_citations(
        decision: PolicyDecision,
        policies: dict[str, PolicyDocument],
    ) -> list[Citation]:
        references = [
            _RULE_CITATIONS[rule_id]
            for rule_id in decision.applicable_rule_ids
            if rule_id in _RULE_CITATIONS
        ]
        if not references:
            references = [("PROCUREMENT_POLICY", "4.1")]

        citations: list[Citation] = []
        seen: set[tuple[str, str]] = set()
        for policy_type, section_id in references:
            policy = policies[policy_type]
            key = (policy.document_id, section_id)
            if key in seen:
                continue
            seen.add(key)
            try:
                section = policy.section(section_id)
            except KeyError as exc:
                raise ApplicablePolicyNotFoundError(
                    f"Policy {policy.document_id} does not define cited section {section_id}"
                ) from exc
            citations.append(
                Citation(
                    document_id=policy.document_id,
                    version=policy.version,
                    title=policy.title,
                    section_id=section_id,
                    section_title=section.title,
                    status=policy.status,
                    effective_from=policy.effective_from,
                )
            )
        return citations

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

    def _case_trace_id(self, approval_id: str) -> str:
        try:
            return self.store.load_case(approval_id)["trace_id"]
        except KeyError:
            return f"trace-{uuid4().hex[:12]}"

    def _audit_decision_failure(
        self,
        exc: ValueBridgeError,
        *,
        approval_id: str,
        target_status: str,
        user: str,
    ) -> None:
        trace_id = self._case_trace_id(approval_id)
        exc.attach_trace(trace_id)
        if isinstance(exc, AuthorizationError):
            self.store.add_audit(
                event_type="APPROVAL_DENIED",
                actor=user[:64],
                approval_id=approval_id[:64],
                trace_id=trace_id,
                details={"target_status": target_status},
            )
            return
        current = self.store.get_approval(approval_id)
        self.store.add_audit(
            event_type="APPROVAL_TRANSITION_FAILED",
            actor=user[:64],
            request_id=current.request_id,
            approval_id=approval_id,
            trace_id=trace_id,
            details={"target_status": target_status, "current_status": current.status},
        )

    def approve(self, approval_id: str, *, role: str, user: str):
        try:
            record = self.store.approve(approval_id, approved_by=user, approver_role=role)
        except (AuthorizationError, InvalidApprovalStateError) as exc:
            self._audit_decision_failure(
                exc,
                approval_id=approval_id,
                target_status="APPROVED",
                user=user,
            )
            raise
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
        payload, idempotency_key = self._build_action(approval, case)
        return ActionPreview(
            approval_id=approval.approval_id,
            target_system="MOCKDESK",
            operation=approval.action_type,
            idempotency_key=idempotency_key,
            payload=payload,
            required_role=approval.required_role,
        )

    @staticmethod
    def _build_action(approval: ApprovalRecord, case: dict) -> tuple[dict[str, object], str]:
        payload: dict[str, object] = {
            "request_id": approval.request_id,
            "summary": "Procurement Exception Review",
            "decision_status": case["decision"]["decision_status"],
            "reasons": case["decision"]["blocking_reasons"],
        }
        return payload, f"{approval.approval_id}-{approval.action_type}"

    def reject(self, approval_id: str, *, role: str, user: str):
        try:
            record = self.store.reject(approval_id, approver_role=role)
        except (AuthorizationError, InvalidApprovalStateError) as exc:
            self._audit_decision_failure(
                exc,
                approval_id=approval_id,
                target_status="REJECTED",
                user=user,
            )
            raise
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
        trace_id = self._case_trace_id(approval_id)
        try:
            authorize(role, "execute_tool_action")
            approval = self.store.require_approved(approval_id)
            case = self.store.load_case(approval_id)
            if approval.case_fingerprint and (
                _case_fingerprint(_decision_context(case)) != approval.case_fingerprint
            ):
                raise ApprovalContextChangedError(
                    f"Approval {approval_id} was granted for a different decision context"
                )
            request_id = approval.request_id
            payload, idempotency_key = self._build_action(approval, case)
            result = self.mockdesk_gateway.create_ticket(
                payload,
                idempotency_key=idempotency_key,
            )
        except AuthorizationError as exc:
            exc.attach_trace(trace_id)
            self.store.add_audit(
                event_type="TOOL_EXECUTION_DENIED",
                actor=user[:64],
                approval_id=approval_id[:64],
                trace_id=trace_id,
                details={"role": role[:64], "action": "execute_tool_action"},
            )
            raise
        except (
            ApprovalRequiredError,
            InvalidApprovalStateError,
            ApprovalContextChangedError,
        ) as exc:
            exc.attach_trace(trace_id)
            blocked = self.store.get_approval(approval_id)
            self.store.add_audit(
                event_type="TOOL_EXECUTION_BLOCKED",
                actor=user[:64],
                request_id=blocked.request_id,
                approval_id=approval_id,
                trace_id=trace_id,
                details={"code": exc.code, "status": blocked.status},
            )
            raise
        except IdempotencyConflictError as exc:
            exc.attach_trace(trace_id)
            self.store.add_audit(
                event_type="TOOL_EXECUTION_CONFLICT",
                actor=user,
                request_id=request_id,
                approval_id=approval_id,
                trace_id=trace_id,
                details={"code": exc.code, "idempotency_key": idempotency_key},
            )
            raise
        except ValueBridgeError as exc:
            exc.attach_trace(trace_id)
            self.store.add_audit(
                event_type="TOOL_EXECUTION_FAILED",
                actor=user,
                request_id=request_id,
                approval_id=approval_id,
                trace_id=trace_id,
                details={"code": exc.code, "error": str(exc), "idempotency_key": idempotency_key},
            )
            raise
        self.store.add_audit(
            event_type="TOOL_EXECUTED",
            actor=user,
            request_id=request_id,
            approval_id=approval_id,
            trace_id=trace_id,
            details=result.model_dump(mode="json"),
        )
        return result
