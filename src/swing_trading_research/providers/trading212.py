"""Read-only client for Trading 212 instrument metadata."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from swing_trading_research.schemas import Trading212Instrument

_INSTRUMENTS_PATH = "/equity/metadata/instruments"


class Trading212Environment(StrEnum):
    """Official Trading 212 API environments."""

    DEMO = "demo"
    LIVE = "live"

    @property
    def base_url(self) -> str:
        """Return the fixed API base URL for this environment."""
        return f"https://{self.value}.trading212.com/api/v0"


class Trading212ClientError(RuntimeError):
    """A safe, user-facing Trading 212 client failure."""


class Trading212ResponseError(Trading212ClientError):
    """Trading 212 returned data that this project cannot safely accept."""


class HttpTransport(Protocol):
    """Small boundary that lets tests replace the real internet connection."""

    def get(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> bytes:
        """Return the response body for one HTTP GET request."""
        ...


class UrllibHttpTransport:
    """Standard-library implementation used for a real API request later."""

    def get(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> bytes:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return response.read()
        except HTTPError as error:
            raise Trading212ClientError(
                f"Trading 212 returned HTTP {error.code}"
            ) from None
        except (URLError, TimeoutError):
            raise Trading212ClientError("Could not reach Trading 212") from None


@dataclass(frozen=True, slots=True)
class Trading212Client:
    """Fetch and validate Trading 212 metadata without exposing credentials."""

    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)
    environment: Trading212Environment = Trading212Environment.DEMO
    timeout_seconds: float = 20.0
    transport: HttpTransport = field(
        default_factory=UrllibHttpTransport,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("api_key cannot be empty")
        if not self.api_secret.strip():
            raise ValueError("api_secret cannot be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    def get_instruments(self) -> tuple[Trading212Instrument, ...]:
        """Retrieve every accessible instrument and validate every item."""
        url = f"{self.environment.base_url}{_INSTRUMENTS_PATH}"
        raw_response = self.transport.get(
            url=url,
            headers=self._headers(),
            timeout_seconds=self.timeout_seconds,
        )

        try:
            payload = json.loads(raw_response)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise Trading212ResponseError("Trading 212 returned invalid JSON") from None

        if not isinstance(payload, list):
            raise Trading212ResponseError(
                "Trading 212 instruments response must be a JSON list"
            )

        instruments: list[Trading212Instrument] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise Trading212ResponseError(
                    f"Trading 212 instrument at index {index} must be an object"
                )
            try:
                instruments.append(Trading212Instrument.from_payload(item))
            except (KeyError, TypeError, ValueError) as error:
                raise Trading212ResponseError(
                    f"Trading 212 instrument at index {index} failed validation: "
                    f"{error}"
                ) from error

        return tuple(instruments)

    def _headers(self) -> dict[str, str]:
        credentials = f"{self.api_key}:{self.api_secret}".encode()
        encoded_credentials = base64.b64encode(credentials).decode("ascii")
        return {
            "Accept": "application/json",
            "Authorization": f"Basic {encoded_credentials}",
            "User-Agent": "swing-trading-research/0.1.0",
        }
