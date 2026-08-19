from datetime import UTC, datetime, timedelta

from app.mockdesk_client import _retry_delay


def test_retry_after_is_capped() -> None:
    assert _retry_delay(0, "3600") == 8.0


def test_negative_retry_after_is_clamped_to_zero() -> None:
    assert _retry_delay(0, "-5") == 0.0


def test_non_finite_retry_after_uses_exponential_fallback() -> None:
    assert _retry_delay(0, "nan") == 0.5


def test_http_date_retry_after_is_supported_and_capped() -> None:
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    retry_at = now + timedelta(seconds=30)
    header = retry_at.strftime("%a, %d %b %Y %H:%M:%S GMT")

    assert _retry_delay(0, header, now=now) == 8.0
