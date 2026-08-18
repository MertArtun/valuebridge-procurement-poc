from __future__ import annotations

import csv
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from statistics import median

from app.models import PurchaseAnalysis, PurchaseRequest


def analyze_purchase_history(
    request: PurchaseRequest,
    purchase_history_path: Path,
    *,
    standard_lead_time_days: int = 14,
) -> PurchaseAnalysis:
    amounts: list[Decimal] = []
    with purchase_history_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["category"] == request.category and row["status"] == "COMPLETED":
                amounts.append(Decimal(row["amount_try"]))

    if not amounts:
        raise ValueError(f"No completed history found for category {request.category}")

    historical_median = Decimal(median(amounts))
    variance = (
        ((request.amount_try - historical_median) / historical_median) * Decimal("100")
    ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    display_variance = variance.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    return PurchaseAnalysis(
        historical_median_try=historical_median,
        variance_percent=variance,
        display_variance_percent=display_variance,
        standard_lead_time_days=standard_lead_time_days,
        lead_time_variance_days=request.offered_lead_time_days - standard_lead_time_days,
    )
