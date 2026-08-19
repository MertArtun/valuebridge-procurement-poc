from datetime import date
from pathlib import Path

import pytest

from app.errors import ApplicablePolicyNotFoundError
from app.retrieval import PolicyRepository


def test_current_policy_is_selected_over_superseded_policy() -> None:
    repository = PolicyRepository(Path("data/documents.json"))

    policy = repository.current_policy(
        policy_type="PROCUREMENT_POLICY",
        on_date=date(2026, 8, 18),
        role="procurement_specialist",
    )

    assert policy.document_id == "PROC-POL-2026"
    assert policy.version == "2026.1"
    assert policy.status == "CURRENT"
    assert "200.000 TL" in policy.section("4.2").body
    assert "100.000 TL" in policy.section("4.3").body


def test_current_supplier_compliance_policy_exposes_certificate_section() -> None:
    repository = PolicyRepository(Path("data/documents.json"))

    policy = repository.current_policy(
        policy_type="SUPPLIER_COMPLIANCE_POLICY",
        on_date=date(2026, 8, 18),
        role="procurement_specialist",
    )

    assert policy.document_id == "SUP-COMP-2026"
    assert policy.version == "2026.1"
    assert policy.status == "CURRENT"
    assert "ISO 9001" in policy.section("3.1").body


def test_dates_outside_the_current_policy_window_are_rejected() -> None:
    repository = PolicyRepository(Path("data/documents.json"))

    with pytest.raises(ApplicablePolicyNotFoundError):
        repository.current_policy(
            policy_type="PROCUREMENT_POLICY",
            on_date=date(2025, 8, 1),
            role="procurement_specialist",
        )


def test_untrusted_supplier_attachment_is_not_a_policy_source() -> None:
    repository = PolicyRepository(Path("data/documents.json"))

    documents = repository.searchable_documents(role="procurement_specialist")

    assert all(document.document_type != "SUPPLIER_ATTACHMENT" for document in documents)
