from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from app.errors import ApplicablePolicyNotFoundError
from app.models import PolicyDocument, PolicySection

_SECTION_PATTERN = re.compile(r"^##\s+(?P<id>[0-9]+(?:\.[0-9]+)*)\s+—\s+(?P<title>.+)$")


class PolicyRepository:
    def __init__(self, manifest_path: Path) -> None:
        self._manifest_path = manifest_path
        self._project_root = manifest_path.parent.parent
        self._entries = json.loads(manifest_path.read_text(encoding="utf-8"))

    def searchable_documents(self, role: str) -> list[PolicyDocument]:
        documents: list[PolicyDocument] = []
        for entry in self._entries:
            if not entry.get("trusted_for_retrieval", False):
                continue
            if role not in entry["allowed_roles"]:
                continue
            documents.append(self._load_document(entry))
        return documents

    def untrusted_attachments(self, supplier_name: str) -> list[tuple[str, str]]:
        """Return (document_id, raw text) pairs for a supplier's untrusted attachments."""
        attachments: list[tuple[str, str]] = []
        for entry in self._entries:
            if entry.get("trusted_for_retrieval", False):
                continue
            if entry.get("supplier_name") != supplier_name:
                continue
            file_path = self._project_root / str(entry["file_path"])
            attachments.append((str(entry["document_id"]), file_path.read_text(encoding="utf-8")))
        return attachments

    def current_policy(self, policy_type: str, on_date: date, role: str) -> PolicyDocument:
        """Return the CURRENT policy effective on ``on_date``.

        The PoC is bounded to the current policy set: only documents with
        status CURRENT are eligible, and the request date must fall inside
        their effective window. Superseded documents stay in the corpus as
        stale-policy exclusion fixtures and are never selected.
        """
        candidates: list[PolicyDocument] = []
        for document in self.searchable_documents(role):
            if document.document_type != policy_type or document.status != "CURRENT":
                continue
            if document.effective_from > on_date:
                continue
            if document.effective_to is not None and document.effective_to < on_date:
                continue
            candidates.append(document)

        if not candidates:
            raise ApplicablePolicyNotFoundError(
                f"No accessible {policy_type} policy is effective for {on_date.isoformat()}"
            )
        candidates.sort(key=lambda item: (item.effective_from, item.version), reverse=True)
        return candidates[0]

    def _load_document(self, entry: dict[str, object]) -> PolicyDocument:
        file_path = self._project_root / str(entry["file_path"])
        sections = _parse_sections(file_path.read_text(encoding="utf-8"))
        return PolicyDocument(**entry, sections=sections)


def _parse_sections(text: str) -> list[PolicySection]:
    sections: list[PolicySection] = []
    current_id: str | None = None
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_id, current_title, current_lines
        if current_id and current_title:
            sections.append(
                PolicySection(
                    section_id=current_id,
                    title=current_title,
                    body="\n".join(current_lines).strip(),
                )
            )
        current_id = None
        current_title = None
        current_lines = []

    for line in text.splitlines():
        match = _SECTION_PATTERN.match(line.strip())
        if match:
            flush()
            current_id = match.group("id")
            current_title = match.group("title")
        elif current_id is not None:
            current_lines.append(line)
    flush()
    return sections
