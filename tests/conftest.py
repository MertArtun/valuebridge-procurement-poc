from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LLM_ENVIRONMENT_VARIABLES = (
    "VALUEBRIDGE_LLM_API_KEY",
    "VALUEBRIDGE_LLM_MODEL",
    "VALUEBRIDGE_LLM_BASE_URL",
    "VALUEBRIDGE_EMBEDDINGS_MODEL",
)


@pytest.fixture(autouse=True)
def keyless_llm_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test against the keyless default, whatever the shell exports."""
    for name in LLM_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def demo_mode_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the hardened demo profile opt-in, whatever the shell exports."""
    monkeypatch.delenv("VALUEBRIDGE_DEMO_MODE", raising=False)
