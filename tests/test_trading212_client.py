"""Offline tests for the read-only Trading 212 client."""

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

import pytest

from swing_trading_research.providers.trading212 import (
    Trading212Client,
    Trading212Environment,
    Trading212ResponseError,
)
from swing_trading_research.schemas import InstrumentType


@dataclass
class FakeTransport:
    """Return a prepared response without making an internet request."""

    response_body: bytes
    calls: list[tuple[str, Mapping[str, str], float]] = field(default_factory=list)

    def get(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> bytes:
        self.calls.append((url, headers, timeout_seconds))
        return self.response_body


def _instrument_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "addedOn": "2019-08-24T14:15:22Z",
        "currencyCode": "USD",
        "extendedHours": True,
        "isin": "US0378331005",
        "maxOpenQuantity": 1000.5,
        "name": "Apple Inc.",
        "shortName": "Apple",
        "ticker": "AAPL_US_EQ",
        "type": "STOCK",
        "workingScheduleId": 1,
    }
    payload.update(changes)
    return payload


def _client(response: object) -> tuple[Trading212Client, FakeTransport]:
    transport = FakeTransport(json.dumps(response).encode("utf-8"))
    client = Trading212Client(
        api_key="test-key",
        api_secret="test-secret",
        transport=transport,
    )
    return client, transport


def test_get_instruments_sends_demo_request_and_validates_response() -> None:
    client, transport = _client(
        [
            _instrument_payload(),
            _instrument_payload(
                currencyCode="GBP",
                extendedHours=False,
                isin="GB0007980591",
                name="BP p.l.c.",
                shortName="BP",
                ticker="BP_GB_EQ",
                workingScheduleId=2,
            ),
        ]
    )

    instruments = client.get_instruments()

    assert len(instruments) == 2
    assert instruments[0].ticker == "AAPL_US_EQ"
    assert instruments[0].instrument_type is InstrumentType.STOCK
    assert instruments[1].ticker == "BP_GB_EQ"
    assert instruments[1].currency_code == "GBP"

    url, headers, timeout = transport.calls[0]
    assert url == ("https://demo.trading212.com/api/v0/equity/metadata/instruments")
    encoded = base64.b64encode(b"test-key:test-secret").decode("ascii")
    assert headers["Authorization"] == f"Basic {encoded}"
    assert headers["Accept"] == "application/json"
    assert timeout == 20.0


def test_live_environment_uses_live_url() -> None:
    transport = FakeTransport(b"[]")
    client = Trading212Client(
        api_key="test-key",
        api_secret="test-secret",
        environment=Trading212Environment.LIVE,
        transport=transport,
    )

    assert client.get_instruments() == ()
    assert transport.calls[0][0].startswith("https://live.trading212.com/api/v0/")


def test_invalid_json_is_rejected() -> None:
    transport = FakeTransport(b"not-json")
    client = Trading212Client(
        api_key="test-key",
        api_secret="test-secret",
        transport=transport,
    )

    with pytest.raises(Trading212ResponseError, match="invalid JSON"):
        client.get_instruments()


def test_non_list_response_is_rejected() -> None:
    client, _transport = _client({"unexpected": "object"})

    with pytest.raises(Trading212ResponseError, match="must be a JSON list"):
        client.get_instruments()


def test_invalid_instrument_reports_its_position() -> None:
    client, _transport = _client([_instrument_payload(currencyCode="US")])

    with pytest.raises(
        Trading212ResponseError,
        match="instrument at index 0 failed validation",
    ):
        client.get_instruments()


def test_client_representation_does_not_reveal_credentials() -> None:
    client, _transport = _client([])

    displayed_client = repr(client)

    assert "test-key" not in displayed_client
    assert "test-secret" not in displayed_client
