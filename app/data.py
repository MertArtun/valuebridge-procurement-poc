from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from app.errors import SupplierNotFoundError
from app.models import SupplierRecord


def load_suppliers(path: Path) -> list[SupplierRecord]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            SupplierRecord(
                supplier_name=row["supplier_name"],
                quality_score=int(row["quality_score"]),
                iso_9001_expiry_date=date.fromisoformat(row["iso_9001_expiry_date"]),
                status=row["status"],
                risk_flag=row["risk_flag"],
            )
            for row in csv.DictReader(handle)
        ]


def load_supplier(path: Path, supplier_name: str) -> SupplierRecord:
    for supplier in load_suppliers(path):
        if supplier.supplier_name == supplier_name:
            return supplier
    raise SupplierNotFoundError(f"Supplier {supplier_name!r} was not found")


def load_purchase_categories(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return sorted({row["category"] for row in csv.DictReader(handle)})
