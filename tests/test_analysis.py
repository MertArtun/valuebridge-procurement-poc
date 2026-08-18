from decimal import Decimal
from pathlib import Path

from app.analysis import analyze_purchase_history
from app.models import PurchaseRequest


def test_hero_scenario_median_and_variance_are_deterministic() -> None:
    request = PurchaseRequest(
        request_id="PR-2026-0042",
        request_date="2026-08-18",
        supplier_name="Atlas Endüstri",
        category="SPARE_PARTS",
        amount_try=Decimal("220000"),
        received_quotes=1,
        offered_lead_time_days=20,
    )

    result = analyze_purchase_history(
        request=request,
        purchase_history_path=Path("data/purchase_history.csv"),
    )

    assert result.historical_median_try == Decimal("184500")
    assert result.variance_percent == Decimal("19.2412")
    assert result.display_variance_percent == Decimal("19.2")
