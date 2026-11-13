"""Read-only client for EODHD daily historical OHLCV data."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from swing_trading_research.schemas import DailyOhlcvBar

_BASE_URL = "https://eodhd.com/api/eod"
_VALID_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9._-]*")


class EodhdClientError(RuntimeError):
    """Safe, user-facing error when fetching data from EODHD."""


class EodhdResponseError(EodhdClientError):
    """EODHD returned an unexpected or invalid response."""


class HttpTransport(Protocol):
    """Network boundary that tests can replace with an offline fake."""

    def get(self, url: str, timeout_seconds: float) -> bytes:
        """Retrieve raw response bytes from an HTTP GET request."""
        ...


class UrllibHttpTransport:
    """Standard-library transport for real requests."""

    def get(self, url: str, timeout_seconds: float) -> bytes:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "swing-trading-research/0.1.0",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return response.read()
        except HTTPError as error:
            # Never expose the URL, because EODHD authenticates in its query string.
            raise EodhdClientError(f"EODHD returned HTTP {error.code}") from None
        except (URLError, TimeoutError):
            raise EodhdClientError("Could not reach EODHD") from None


@dataclass(frozen=True, slots=True)
class EodhdDailyHistory:
    """Historical response with both validated bars and original provider bytes."""

    symbol: str
    start_date: date
    end_date: date
    raw_response: bytes = field(repr=False)
    bars: tuple[DailyOhlcvBar, ...]
    request_parameters: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class EodhdClient:
    """Fetch daily EODHD data without placing secrets in logs or metadata."""

    api_token: str = field(repr=False)
    timeout_seconds: float = 20.0
    transport: HttpTransport = field(
        default_factory=UrllibHttpTransport,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not self.api_token.strip():
            raise ValueError("api_token cannot be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    def get_daily_history(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> EodhdDailyHistory:
        """Fetch ascending daily bars in an inclusive date range."""
        normalized_symbol = symbol.strip().upper()
        if not _VALID_SYMBOL.fullmatch(normalized_symbol):
            raise ValueError("symbol has invalid characters")
        if start_date > end_date:
            raise ValueError("start_date cannot be after end_date")

        # Deliberately exclude api_token: these parameters are safe to persist.
        parameters = (
            ("from", start_date.isoformat()),
            ("to", end_date.isoformat()),
            ("period", "d"),
            ("order", "a"),
            ("fmt", "json"),
        )
        query = urlencode((("api_token", self.api_token), *parameters))
        url = f"{_BASE_URL}/{normalized_symbol}?{query}"
        raw_response = self.transport.get(url, self.timeout_seconds)

        try:
            # Decimal avoids introducing binary-float rounding during JSON parsing.
            payload = json.loads(raw_response, parse_float=Decimal)
        except (UnicodeDecodeError, ValueError):
            raise EodhdResponseError("EODHD returned invalid JSON") from None

        if not isinstance(payload, list):
            raise EodhdResponseError("EODHD daily response must be a JSON list")

        bars: list[DailyOhlcvBar] = []
        last_date: date | None = None
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise EodhdResponseError(
                    f"EODHD bar at index {index} must be an object"
                )
            try:
                bar = DailyOhlcvBar.from_eodhd_payload(item)
            except (KeyError, TypeError, ValueError) as error:
                raise EodhdResponseError(
                    f"EODHD bar at index {index} failed validation: {error}"
                ) from error
            if not start_date <= bar.trading_date <= end_date:
                raise EodhdResponseError(
                    f"EODHD bar at index {index} is outside the requested range"
                )
            if last_date is not None and bar.trading_date <= last_date:
                raise EodhdResponseError(
                    f"EODHD bar at index {index} is duplicate or out of order"
                )
            bars.append(bar)
            last_date = bar.trading_date

        # An empty series is valid (for example, a weekend-only date range).
        return EodhdDailyHistory(
            symbol=normalized_symbol,
            start_date=start_date,
            end_date=end_date,
            raw_response=raw_response,
            bars=tuple(bars),
            request_parameters=parameters,
        )
