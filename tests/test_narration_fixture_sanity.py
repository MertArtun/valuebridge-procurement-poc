"""The recorded narration is the first prose a reader meets in the demo.

It is a hand-maintained placeholder, so nothing but a test stops it from
attributing a figure to the wrong comparison or a rule to the wrong section.
"""

import json
import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "llm_transcripts.json"
HERO_NARRATION_KEY = "a3220437f667b8a7"


def narration() -> str:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))[HERO_NARRATION_KEY]


def sentence_with(needle: str) -> str:
    sentences = [part.strip() for part in re.split(r"(?<=\.)\s+", narration()) if part.strip()]
    matching = [part for part in sentences if needle in part]
    assert len(matching) == 1, f"{needle!r} belongs in exactly one sentence, found {matching}"
    return matching[0].lower()


def test_the_price_variance_is_attributed_to_the_historical_median() -> None:
    sentence = sentence_with("%19,2")

    assert "medyan" in sentence
    assert "teslim" not in sentence
    assert "tedarik süresi" not in sentence


def test_the_lead_time_deviation_is_stated_in_days_and_never_as_a_percentage() -> None:
    sentence = sentence_with("6 gün")

    assert "teslim" in sentence or "tedarik süresi" in sentence
    assert "14 gün" in sentence
    assert "%" not in sentence


def test_each_rule_cites_the_section_that_actually_carries_it() -> None:
    assert "finans onayı" in sentence_with("4.2")
    assert "teklif" in sentence_with("4.3")
    assert "sertifika" in sentence_with("3.1")


def test_the_alternative_quote_rule_is_not_filed_under_the_finance_section() -> None:
    assert "alternatif teklif" not in sentence_with("4.2")
