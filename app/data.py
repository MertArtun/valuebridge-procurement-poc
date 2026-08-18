from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from app.models import SupplierRecord


def load_supplier(path: Path, supplier_name: str) -> SupplierRecord:
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["supplier_name"] == supplier_name:
                return SupplierRecord(
                    supplier_name=row["supplier_name"],
                    quality_score=int(row["quality_score"]),
                    iso_9001_expiry_date=date.fromisoformat(row["iso_9001_expiry_date"]),
                    status=row["status"],
                    risk_flag=row["risk_flag"],
                )
    raise ValueError(f"Supplier {supplier_name!r} was not found")
