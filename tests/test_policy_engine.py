from datetime import date
from decimal import Decimal
from pathlib import Path

from app.models import PurchaseAnalysis, PurchaseRequest, SupplierRecord
from app.policy_engine import PolicyEngine


def test_hero_scenario_requires_conditional_review() -> None:
    request = PurchaseRequest(
        request_id="PR-2026-0042",
        request_date="2026-08-18",
        supplier_name="Atlas Endüstri",
        category="SPARE_PARTS",
        amount_try=Decimal("220000"),
        received_quotes=1,
        offered_lead_time_days=20,
    )
    analysis = PurchaseAnalysis(
        historical_median_try=Decimal("184500"),
        variance_percent=Decimal("19.2412"),
        display_variance_percent=Decimal("19.2"),
        standard_lead_time_days=14,
        lead_time_variance_days=6,
    )
    supplier = SupplierRecord(
        supplier_name="Atlas Endüstri",
        quality_score=82,
        iso_9001_expiry_date=date(2026, 6, 30),
        status="active",
        risk_flag="certificate_expired",
    )

    decision = PolicyEngine.from_yaml(Path("data/policy_rules.yaml")).evaluate(
        request=request,
        analysis=analysis,
        supplier=supplier,
    )

    assert decision.decision_status == "CONDITIONAL_REVIEW"
    assert decision.finance_approval_required is True
    assert decision.alternative_quote_missing is True
    assert decision.certificate_status == "EXPIRED"
    assert decision.lead_time_variance_days == 6
    assert set(decision.applicable_rule_ids) == {
        "FINANCE_APPROVAL",
        "ALTERNATIVE_QUOTES",
        "SUPPLIER_CERTIFICATE",
    }
