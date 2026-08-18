from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

from app.models import PolicyDecision, PurchaseAnalysis, PurchaseRequest, SupplierRecord


class PolicyEngine:
    def __init__(self, rules: dict[str, object]) -> None:
        self._rules = rules

    @classmethod
    def from_yaml(cls, path: Path) -> PolicyEngine:
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")))

    def evaluate(
        self,
        request: PurchaseRequest,
        analysis: PurchaseAnalysis,
        supplier: SupplierRecord,
    ) -> PolicyDecision:
        finance_threshold = Decimal(str(self._rules["finance_approval"]["threshold_try"]))
        quote_threshold = Decimal(str(self._rules["alternative_quotes"]["threshold_try"]))
        minimum_quotes = int(self._rules["alternative_quotes"]["minimum_quotes"])

        finance_required = request.amount_try > finance_threshold
        quote_missing = (
            request.amount_try > quote_threshold and request.received_quotes < minimum_quotes
        )
        certificate_status = _certificate_status(
            supplier.iso_9001_expiry_date,
            request.request_date,
        )

        reasons: list[str] = []
        warnings: list[str] = []
        rules: list[str] = []
        if finance_required:
            reasons.append("Talep tutarı finans yöneticisi onay sınırını aşıyor.")
            rules.append("FINANCE_APPROVAL")
        if quote_missing:
            reasons.append("Zorunlu alternatif teklif sayısı karşılanmıyor.")
            rules.append("ALTERNATIVE_QUOTES")
        if certificate_status != "VALID":
            reasons.append(
                "Tedarikçinin zorunlu ISO 9001 sertifikası talep tarihinde geçerli değil."
            )
            rules.append("SUPPLIER_CERTIFICATE")
        if analysis.variance_percent > Decimal("0"):
            warnings.append(
                f"Teklif geçmiş kategori medyanının %{analysis.display_variance_percent} üzerinde."
            )
        if analysis.lead_time_variance_days > 0:
            warnings.append(
                "Teklif edilen teslim süresi standart süreden "
                f"{analysis.lead_time_variance_days} gün uzun."
            )

        status = "CONDITIONAL_REVIEW" if reasons else "APPROVED"
        return PolicyDecision(
            decision_status=status,
            finance_approval_required=finance_required,
            alternative_quote_missing=quote_missing,
            certificate_status=certificate_status,
            lead_time_variance_days=analysis.lead_time_variance_days,
            blocking_reasons=reasons,
            warnings=warnings,
            applicable_rule_ids=rules,
        )


def _certificate_status(expiry_date: date, request_date: date) -> str:
    return "VALID" if expiry_date >= request_date else "EXPIRED"
