"""Governed policy question answering: retrieval is scoped before it is scored.

Only trusted documents a role may read, with status CURRENT and an effective
window covering the asked date, ever become retrieval candidates. Superseded
policy and untrusted supplier attachments are excluded before any lexical or
vector score is computed, so no ranking signal can promote them back in.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Protocol

import httpx

from app.errors import ApplicablePolicyNotFoundError, LlmUnavailableError
from app.llm import DEFAULT_BASE_URL, ChatClient, load_prompt
from app.models import PolicyDocument, PolicySection
from app.retrieval import PolicyRepository

DEFAULT_EMBEDDINGS_MODEL = "openai/text-embedding-3-small"

_K1 = 1.5
_B = 0.75
_TOP_K = 3
_SNIPPET_CHARS = 240
_LEXICAL_WEIGHT = 0.5
_VECTOR_WEIGHT = 0.5
_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)
_MIN_TOKEN_LENGTH = 2
# str.casefold maps İ to "i" + U+0307, a combining mark \w does not match, which
# would split the word and drop the leading letter. Lowercase Turkish first.
_TURKISH_LOWERCASE = str.maketrans({"İ": "i", "I": "ı"})
_STOPWORDS = frozenset(
    {
        "ve",
        "ile",
        "için",
        "bir",
        "bu",
        "da",
        "de",
        "mi",
        "ne",
        "kaç",
        "hangi",
        "nasıl",
        "en",
        "az",
        "çok",
        "olan",
        "olarak",
        "üzerinde",
        "altında",
        "gerekir",
        "midir",
        "mıdır",
        "ise",
        "veya",
        "ama",
    }
)

Candidate = tuple[PolicyDocument, PolicySection]


def _tokenize(text: str) -> list[str]:
    folded = text.translate(_TURKISH_LOWERCASE).casefold()
    return [
        token
        for token in _TOKEN_PATTERN.findall(folded)
        if len(token) >= _MIN_TOKEN_LENGTH and token not in _STOPWORDS
    ]


def _bm25_scores(query: list[str], documents: list[list[str]]) -> list[float]:
    total = len(documents)
    scores = [0.0] * total
    if not total:
        return scores
    lengths = [len(tokens) for tokens in documents]
    average = (sum(lengths) / total) or 1.0
    frequencies = [Counter(tokens) for tokens in documents]
    for term in set(query):
        document_frequency = sum(1 for counts in frequencies if term in counts)
        if not document_frequency:
            continue
        idf = math.log(1 + (total - document_frequency + 0.5) / (document_frequency + 0.5))
        for index, counts in enumerate(frequencies):
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            saturation = _K1 * (1 - _B + _B * lengths[index] / average)
            scores[index] += idf * frequency * (_K1 + 1) / (frequency + saturation)
    return scores


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lowest = min(values)
    span = max(values) - lowest
    if span == 0:
        return [0.0] * len(values)
    return [(value - lowest) / span for value in values]


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    magnitude = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if not magnitude:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / magnitude


class EmbeddingClient(Protocol):
    def embed(self, text: str) -> list[float]: ...


class OpenRouterEmbeddingClient:
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

    def embed(self, text: str) -> list[float]:
        payload = {"model": self.model, "input": [text]}
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/embeddings",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError as exc:
            # Provider transport errors carry hosts, proxies and occasionally
            # credentials; surface the failure class only.
            raise LlmUnavailableError(
                f"Embedding provider transport failure ({type(exc).__name__})"
            ) from exc
        if response.is_error:
            # The provider body may echo the embedded text; the status code is
            # the only part safe to hand back or audit.
            raise LlmUnavailableError(f"Embedding provider returned HTTP {response.status_code}")
        return _embedding_vector(response)


def embedding_client_from_env() -> EmbeddingClient | None:
    api_key = os.getenv("VALUEBRIDGE_LLM_API_KEY")
    if not api_key:
        return None
    return OpenRouterEmbeddingClient(
        api_key=api_key,
        model=os.getenv("VALUEBRIDGE_EMBEDDINGS_MODEL", DEFAULT_EMBEDDINGS_MODEL),
        base_url=os.getenv("VALUEBRIDGE_LLM_BASE_URL", DEFAULT_BASE_URL),
    )


def _embedding_vector(response: httpx.Response) -> list[float]:
    try:
        vector = response.json()["data"][0]["embedding"]
        return [float(value) for value in vector]
    except (ValueError, LookupError, TypeError) as exc:
        raise LlmUnavailableError(
            f"Embedding provider returned an unreadable vector (HTTP {response.status_code})"
        ) from exc


class PolicyQaService:
    def __init__(
        self,
        repository: PolicyRepository,
        chat_client: ChatClient | None = None,
        embedding_client: EmbeddingClient | None = None,
        embeddings_path: Path | None = None,
    ) -> None:
        self.repository = repository
        self.chat_client = chat_client
        self.embedding_client = embedding_client
        self.embeddings_path = embeddings_path

    def ask(self, question: str, *, on_date: date, role: str) -> dict[str, object]:
        candidates = self._candidates(role, on_date)
        lexical = _bm25_scores(
            _tokenize(question),
            [_tokenize(f"{section.title}\n{section.body}") for _, section in candidates],
        )
        scores, retrieval_mode = self._score(question, candidates, lexical)
        ranked = sorted(
            zip(candidates, scores, strict=True),
            key=lambda item: item[1],
            reverse=True,
        )
        top = [(candidate, score) for candidate, score in ranked[:_TOP_K] if score > 0]
        return {
            "retrieval_mode": retrieval_mode,
            "sections": [
                {
                    "document_id": document.document_id,
                    "version": document.version,
                    "title": document.title,
                    "section_id": section.section_id,
                    "section_title": section.title,
                    "score": round(score, 4),
                    "snippet": section.body[:_SNIPPET_CHARS],
                }
                for (document, section), score in top
            ],
            "answer": self._answer(question, top),
        }

    def _candidates(self, role: str, on_date: date) -> list[Candidate]:
        candidates: list[Candidate] = []
        for document in self.repository.searchable_documents(role):
            if document.status != "CURRENT" or document.effective_from > on_date:
                continue
            if document.effective_to is not None and document.effective_to < on_date:
                continue
            candidates.extend((document, section) for section in document.sections)
        if not candidates:
            raise ApplicablePolicyNotFoundError(
                f"No accessible policy section is effective for {on_date.isoformat()}"
            )
        return candidates

    def _score(
        self,
        question: str,
        candidates: list[Candidate],
        lexical: list[float],
    ) -> tuple[list[float], str]:
        if (
            self.embedding_client is None
            or self.embeddings_path is None
            or not self.embeddings_path.exists()
        ):
            return lexical, "lexical"
        try:
            vectors = _load_vectors(self.embeddings_path)
            query = self.embedding_client.embed(question)
        except Exception:
            # The vector layer only reorders an already governed candidate set:
            # a missing, malformed or unreachable index degrades to lexical.
            return lexical, "lexical"
        hybrid: list[float] = []
        for normalized, (document, section) in zip(_minmax(lexical), candidates, strict=True):
            vector = vectors.get((document.document_id, section.section_id), [])
            hybrid.append(
                _LEXICAL_WEIGHT * normalized + _VECTOR_WEIGHT * _cosine(query, vector)
            )
        return hybrid, "hybrid"

    def _answer(self, question: str, top: list[tuple[Candidate, float]]) -> str | None:
        if self.chat_client is None or not top:
            return None
        try:
            answer = self.chat_client.complete(
                system=load_prompt("policy_qa_system"),
                user=_answer_user_message(question, top),
            )
        except Exception:
            # The answer is display-only: the retrieved sections already stand
            # on their own and must never be lost to a failing provider.
            return None
        return answer.strip() or None


def _load_vectors(path: Path) -> dict[tuple[str, str], list[float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        (str(item["document_id"]), str(item["section_id"])): [
            float(value) for value in item["embedding"]
        ]
        for item in payload["sections"]
    }


def _answer_user_message(question: str, top: list[tuple[Candidate, float]]) -> str:
    parts = [f"Soru: {question}"]
    for (document, section), _score in top:
        parts.append(
            f"--- POLİTİKA BÖLÜMÜ §{section.section_id} — {section.title} "
            f"({document.document_id} v{document.version}) ---\n{section.body}"
        )
    return "\n\n".join(parts)
