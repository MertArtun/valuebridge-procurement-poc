from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Protocol

import httpx

from app.errors import LlmUnavailableError

DEFAULT_MODEL = "anthropic/claude-sonnet-5"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_MAX_TOKENS = 1024
_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


class ChatClient(Protocol):
    def complete(self, *, system: str, user: str) -> str: ...


def prompt_key(system: str, user: str) -> str:
    digest = hashlib.sha256((system + "\x00" + user).encode("utf-8")).hexdigest()
    return digest[:16]


def load_prompt(name: str) -> str:
    return (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


class OpenRouterChatClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def complete(self, *, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": _MAX_TOKENS,
            "temperature": 0,
        }
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError as exc:
            # Provider transport errors carry hosts, proxies and occasionally
            # credentials; surface the failure class only.
            raise LlmUnavailableError(
                f"LLM provider transport failure ({type(exc).__name__})"
            ) from exc
        if response.is_error:
            # The provider body may echo the prompt or internal details; the
            # status code is the only part safe to hand back or audit.
            raise LlmUnavailableError(f"LLM provider returned HTTP {response.status_code}")
        return _completion_content(response)


class RecordedChatClient:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._transcripts = json.loads(path.read_text(encoding="utf-8"))

    def complete(self, *, system: str, user: str) -> str:
        key = prompt_key(system, user)
        content = self._transcripts.get(key)
        if not isinstance(content, str):
            raise LlmUnavailableError(
                f"No recorded LLM transcript for prompt {key}; "
                "run scripts/record_llm_fixtures.py to refresh them"
            )
        return content


def chat_client_from_env() -> ChatClient | None:
    api_key = os.getenv("VALUEBRIDGE_LLM_API_KEY")
    if not api_key:
        return None
    return OpenRouterChatClient(
        api_key=api_key,
        model=os.getenv("VALUEBRIDGE_LLM_MODEL", DEFAULT_MODEL),
        base_url=os.getenv("VALUEBRIDGE_LLM_BASE_URL", DEFAULT_BASE_URL),
    )


def _completion_content(response: httpx.Response) -> str:
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, LookupError, TypeError) as exc:
        raise LlmUnavailableError(
            f"LLM provider returned an unreadable completion (HTTP {response.status_code})"
        ) from exc
    if not isinstance(content, str):
        raise LlmUnavailableError(
            f"LLM provider returned a non-text completion (HTTP {response.status_code})"
        )
    return content
