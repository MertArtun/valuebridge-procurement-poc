from __future__ import annotations

import csv
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from statistics import median

from app.errors import PurchaseHistoryInvalidError, PurchaseHistoryNotFoundError
from app.models import PurchaseAnalysis, PurchaseRequest


def analyze_purchase_history(
    request: PurchaseRequest,
    purchase_history_path: Path,
    *,
    standard_lead_time_days: int = 14,
) -> PurchaseAnalysis:
    amounts: list[Decimal] = []
    with purchase_history_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row["category"] != request.category or row["status"] != "COMPLETED":
                continue
            try:
                purchase_date = date.fromisoformat(row["purchase_date"])
            except ValueError as exc:
                raise PurchaseHistoryInvalidError(
                    f"Invalid purchase_date at line {reader.line_num} "
                    f"of {purchase_history_path.name}"
                ) from exc
            if purchase_date <= request.request_date:
                try:
                    amounts.append(Decimal(row["amount_try"]))
                except InvalidOperation as exc:
                    raise PurchaseHistoryInvalidError(
                        f"Invalid amount_try at line {reader.line_num} "
                        f"of {purchase_history_path.name}"
                    ) from exc

    if not amounts:
        raise PurchaseHistoryNotFoundError(
            f"No completed history found for category {request.category!r} "
            f"on or before {request.request_date.isoformat()}"
        )

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
