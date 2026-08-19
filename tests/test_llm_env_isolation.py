from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from app.llm import chat_client_from_env
from app.policy_qa import embedding_client_from_env

AMBIENT_CREDENTIALS = {
    "VALUEBRIDGE_LLM_API_KEY": "ambient-shell-key",
    "VALUEBRIDGE_LLM_MODEL": "ambient/model",
    "VALUEBRIDGE_LLM_BASE_URL": "https://ambient.test/v1",
    "VALUEBRIDGE_EMBEDDINGS_MODEL": "ambient/embeddings",
}


@pytest.fixture(scope="module", autouse=True)
def ambient_provider_credentials() -> Iterator[None]:
    # Module scope is set up before the function-scoped conftest guard, so this
    # stands in for a developer shell that already exports live credentials.
    previous = {name: os.environ.get(name) for name in AMBIENT_CREDENTIALS}
    os.environ.update(AMBIENT_CREDENTIALS)
    yield
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def test_ambient_provider_credentials_never_reach_a_test() -> None:
    assert [name for name in AMBIENT_CREDENTIALS if name in os.environ] == []
    assert chat_client_from_env() is None
    assert embedding_client_from_env() is None
