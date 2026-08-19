from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.errors import LlmUnavailableError
from app.llm import OpenRouterChatClient, RecordedChatClient, chat_client_from_env, prompt_key
from scripts.record_llm_fixtures import FIXTURE_PATH, canonical_prompts

COMPLETION = {"choices": [{"message": {"role": "assistant", "content": "Karar açıklaması."}}]}


def build_client(handler) -> tuple[OpenRouterChatClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = OpenRouterChatClient(
        api_key="test-key",
        model="anthropic/claude-sonnet-5",
        base_url="https://openrouter.test/api/v1",
        transport=httpx.MockTransport(recording),
    )
    return client, requests


def test_completion_posts_both_turns_with_a_deterministic_temperature() -> None:
    client, requests = build_client(lambda _request: httpx.Response(200, json=COMPLETION))

    answer = client.complete(system="sistem", user="kullanıcı")

    assert answer == "Karar açıklaması."
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://openrouter.test/api/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key"
    payload = json.loads(request.content)
    assert payload["model"] == "anthropic/claude-sonnet-5"
    assert payload["temperature"] == 0
    assert payload["max_tokens"] == 1024
    assert payload["messages"] == [
        {"role": "system", "content": "sistem"},
        {"role": "user", "content": "kullanıcı"},
    ]


def test_http_error_status_never_echoes_the_provider_body() -> None:
    secret = "traceback with sk-live-provider-secret"
    client, _ = build_client(
        lambda _request: httpx.Response(500, json={"error": {"message": secret}})
    )

    with pytest.raises(LlmUnavailableError) as raised:
        client.complete(system="sistem", user="kullanıcı")

    assert "500" in str(raised.value)
    assert secret not in str(raised.value)
    assert raised.value.status_code == 502
    assert raised.value.retryable is True


def test_transport_error_surfaces_as_llm_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused to 10.0.0.7", request=request)

    client, _ = build_client(handler)

    with pytest.raises(LlmUnavailableError) as raised:
        client.complete(system="sistem", user="kullanıcı")

    assert "10.0.0.7" not in str(raised.value)


def test_unparseable_completion_body_surfaces_as_llm_unavailable() -> None:
    client, _ = build_client(lambda _request: httpx.Response(200, json={"choices": []}))

    with pytest.raises(LlmUnavailableError):
        client.complete(system="sistem", user="kullanıcı")


def test_recorded_client_replays_every_canonical_prompt_pair() -> None:
    client = RecordedChatClient(FIXTURE_PATH)

    pairs = canonical_prompts()
    assert pairs
    for system, user in pairs:
        assert client.complete(system=system, user=user).strip()


def test_recorded_client_miss_points_the_operator_at_the_record_script(tmp_path: Path) -> None:
    path = tmp_path / "transcripts.json"
    path.write_text(json.dumps({prompt_key("a", "b"): "cevap"}), encoding="utf-8")
    client = RecordedChatClient(path)

    assert client.complete(system="a", user="b") == "cevap"
    with pytest.raises(LlmUnavailableError) as raised:
        client.complete(system="a", user="c")
    assert "scripts/record_llm_fixtures.py" in str(raised.value)


def test_client_is_absent_until_an_api_key_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VALUEBRIDGE_LLM_API_KEY", raising=False)

    assert chat_client_from_env() is None

    monkeypatch.setenv("VALUEBRIDGE_LLM_API_KEY", "test-key")
    monkeypatch.delenv("VALUEBRIDGE_LLM_MODEL", raising=False)
    monkeypatch.delenv("VALUEBRIDGE_LLM_BASE_URL", raising=False)
    default_client = chat_client_from_env()
    assert isinstance(default_client, OpenRouterChatClient)
    assert default_client.model == "anthropic/claude-sonnet-5"
    assert default_client.base_url == "https://openrouter.ai/api/v1"

    monkeypatch.setenv("VALUEBRIDGE_LLM_MODEL", "vendor/model-x")
    monkeypatch.setenv("VALUEBRIDGE_LLM_BASE_URL", "https://gateway.test/v1")
    configured = chat_client_from_env()
    assert configured.model == "vendor/model-x"
    assert configured.base_url == "https://gateway.test/v1"
