"""Offline tests for the read-only EODHD historical data client."""

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import pytest

from swing_trading_research.providers.eodhd import (
    EodhdClient,
    EodhdResponseError,
)


@dataclass
class FakeTransport:
    """Return a synthetic response without contacting a live API."""

    response: bytes
    calls: list[tuple[str, float]] = field(default_factory=list)

    def get(self, url: str, timeout_seconds: float) -> bytes:
        self.calls.append((url, timeout_seconds))
        return self.response


def _bar(**changes: object) -> dict[str, object]:
    item: dict[str, object] = {
        "date": "2026-11-09",
        "open": 100.1,
        "high": 102.3,
        "low": 99.8,
        "close": 101.2,
        "adjusted_close": 100.9,
        "volume": 1200,
    }
    item.update(changes)
    return item


def _client(payload: object) -> tuple[EodhdClient, FakeTransport]:
    transport = FakeTransport(json.dumps(payload).encode("utf-8"))
    return EodhdClient(api_token="synthetic-test-token", transport=transport), transport


def test_fetch_daily_history_preserves_bytes_and_validates_bars() -> None:
    client, transport = _client([_bar(date="2026-11-06"), _bar(date="2026-11-09")])

    result = client.get_daily_history("aapl.us", date(2026, 11, 6), date(2026, 11, 9))

    assert result.symbol == "AAPL.US"
    assert len(result.bars) == 2
    assert result.bars[0].close_raw == Decimal("101.2")
    assert result.bars[0].close_adjusted == Decimal("100.9")
    assert result.bars[0].volume_split_adjusted == 1200
    assert json.loads(result.raw_response) == [
        _bar(date="2026-11-06"),
        _bar(date="2026-11-09"),
    ]
    assert ("api_token", "synthetic-test-token") not in result.request_parameters

    url, timeout = transport.calls[0]
    assert urlsplit(url).path == "/api/eod/AAPL.US"
    assert parse_qs(urlsplit(url).query) == {
        "api_token": ["synthetic-test-token"],
        "from": ["2026-11-06"],
        "to": ["2026-11-09"],
        "period": ["d"],
        "order": ["a"],
        "fmt": ["json"],
    }
    assert timeout == 20.0


def test_uk_symbol_is_not_automatically_converted_to_gbp() -> None:
    client, transport = _client([_bar()])

    result = client.get_daily_history("BP.LSE", date(2026, 11, 9), date(2026, 11, 9))

    assert result.symbol == "BP.LSE"
    assert result.bars[0].close_raw == Decimal("101.2")
    assert urlsplit(transport.calls[0][0]).path == "/api/eod/BP.LSE"


def test_client_representation_does_not_expose_token() -> None:
    client, _ = _client([])
    assert "synthetic-test-token" not in repr(client)


@pytest.mark.parametrize("symbol", ["", "AAPL.US?bad=x", "../secrets"])
def test_rejects_invalid_symbols(symbol: str) -> None:
    client, transport = _client([])
    with pytest.raises(ValueError, match="invalid characters"):
        client.get_daily_history(symbol, date(2026, 11, 9), date(2026, 11, 9))
    assert transport.calls == []


def test_rejects_reversed_date_range_before_http_request() -> None:
    client, transport = _client([])
    with pytest.raises(ValueError, match="start_date"):
        client.get_daily_history("AAPL.US", date(2026, 11, 10), date(2026, 11, 9))
    assert transport.calls == []


def test_invalid_json_is_rejected() -> None:
    client = EodhdClient(api_token="test", transport=FakeTransport(b"not-json"))
    with pytest.raises(EodhdResponseError, match="invalid JSON"):
        client.get_daily_history("AAPL.US", date(2026, 11, 9), date(2026, 11, 9))


def test_non_list_response_is_rejected() -> None:
    client, _ = _client({"error": "invalid symbol"})
    with pytest.raises(EodhdResponseError, match="JSON list"):
        client.get_daily_history("AAPL.US", date(2026, 11, 9), date(2026, 11, 9))


def test_bad_ohlc_is_rejected_by_existing_schema() -> None:
    client, _ = _client([_bar(high=98)])
    with pytest.raises(EodhdResponseError, match="failed validation"):
        client.get_daily_history("AAPL.US", date(2026, 11, 9), date(2026, 11, 9))


def test_duplicate_dates_are_rejected() -> None:
    client, _ = _client([_bar(), _bar()])
    with pytest.raises(EodhdResponseError, match="duplicate or out of order"):
        client.get_daily_history("AAPL.US", date(2026, 11, 9), date(2026, 11, 9))


def test_out_of_range_dates_are_rejected() -> None:
    client, _ = _client([_bar(date="2026-11-10")])
    with pytest.raises(EodhdResponseError, match="outside the requested range"):
        client.get_daily_history("AAPL.US", date(2026, 11, 9), date(2026, 11, 9))


def test_empty_weekend_response_is_valid() -> None:
    client, _ = _client([])
    result = client.get_daily_history("AAPL.US", date(2026, 11, 7), date(2026, 11, 8))
    assert result.bars == ()
    assert result.raw_response == b"[]"
