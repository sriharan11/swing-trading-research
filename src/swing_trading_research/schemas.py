"""Validated data contracts for broker metadata and daily market data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Self

_CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")
_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SECRET_PARAMETER_FRAGMENTS = (
    "api_key",
    "apikey",
    "api_token",
    "authorization",
    "password",
    "secret",
    "token",
)


class InstrumentType(StrEnum):
    """Instrument types currently documented by the Trading 212 API."""

    STOCK = "STOCK"
    ETF = "ETF"
    WARRANT = "WARRANT"
    CRYPTOCURRENCY = "CRYPTOCURRENCY"
    FOREX = "FOREX"
    FUTURES = "FUTURES"
    INDEX = "INDEX"
    CRYPTO = "CRYPTO"
    CVR = "CVR"
    CORPACT = "CORPACT"


class MappingMethod(StrEnum):
    """Evidence used to connect a broker instrument to a data-provider symbol."""

    ISIN = "isin"
    TICKER_EXCHANGE = "ticker_exchange"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class QuoteConvention:
    """Describe the unit in which an instrument price is quoted."""

    quote_unit: str
    major_currency: str
    units_per_major: Decimal

    def __post_init__(self) -> None:
        _validate_currency_code(self.quote_unit, "quote_unit")
        _validate_currency_code(self.major_currency, "major_currency")
        if self.units_per_major <= 0:
            raise ValueError("units_per_major must be positive")

    @classmethod
    def from_code(cls, code: str) -> Self:
        """Create the convention for a provider currency or quote-unit code."""
        normalized = code.strip().upper()
        _validate_currency_code(normalized, "code")
        if normalized == "GBX":
            return cls(
                quote_unit="GBX",
                major_currency="GBP",
                units_per_major=Decimal("100"),
            )
        return cls(
            quote_unit=normalized,
            major_currency=normalized,
            units_per_major=Decimal("1"),
        )

    def to_major(self, amount: Decimal) -> Decimal:
        """Convert a quoted amount to its major currency without rounding."""
        return amount / self.units_per_major


@dataclass(frozen=True, slots=True)
class Trading212Instrument:
    """One instrument returned by Trading 212's instrument metadata endpoint."""

    added_on: datetime
    currency_code: str
    extended_hours: bool
    isin: str | None
    max_open_quantity: Decimal
    name: str
    short_name: str
    ticker: str
    instrument_type: InstrumentType
    working_schedule_id: int

    def __post_init__(self) -> None:
        _validate_aware_datetime(self.added_on, "added_on")
        _validate_currency_code(self.currency_code, "currency_code")
        if self.isin is not None and not _ISIN.fullmatch(self.isin):
            raise ValueError("isin must be a 12-character uppercase ISIN or None")
        if self.max_open_quantity < 0:
            raise ValueError("max_open_quantity cannot be negative")
        _validate_non_empty(self.name, "name")
        _validate_non_empty(self.short_name, "short_name")
        _validate_non_empty(self.ticker, "ticker")
        if self.working_schedule_id < 0:
            raise ValueError("working_schedule_id cannot be negative")

    @property
    def quote_convention(self) -> QuoteConvention:
        """Return the explicit conversion rule for this instrument's quote unit."""
        return QuoteConvention.from_code(self.currency_code)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        """Parse and validate one Trading 212 JSON response item."""
        raw_isin = payload["isin"]
        isin_value = None if raw_isin is None else str(raw_isin).strip().upper()
        return cls(
            added_on=_parse_datetime(payload["addedOn"], "addedOn"),
            currency_code=str(payload["currencyCode"]).strip().upper(),
            extended_hours=_require_bool(payload["extendedHours"], "extendedHours"),
            isin=isin_value or None,
            max_open_quantity=_parse_decimal(
                payload["maxOpenQuantity"], "maxOpenQuantity"
            ),
            name=str(payload["name"]).strip(),
            short_name=str(payload["shortName"]).strip(),
            ticker=str(payload["ticker"]).strip(),
            instrument_type=InstrumentType(str(payload["type"]).strip().upper()),
            working_schedule_id=_parse_int(
                payload["workingScheduleId"], "workingScheduleId"
            ),
        )


@dataclass(frozen=True, slots=True)
class DailyOhlcvBar:
    """Canonical daily bar with adjustment semantics encoded in field names."""

    trading_date: date
    open_raw: Decimal
    high_raw: Decimal
    low_raw: Decimal
    close_raw: Decimal
    close_adjusted: Decimal
    volume_split_adjusted: int

    def __post_init__(self) -> None:
        prices = {
            "open_raw": self.open_raw,
            "high_raw": self.high_raw,
            "low_raw": self.low_raw,
            "close_raw": self.close_raw,
            "close_adjusted": self.close_adjusted,
        }
        for field_name, value in prices.items():
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")
        if self.low_raw > min(self.open_raw, self.close_raw):
            raise ValueError("low_raw cannot exceed open_raw or close_raw")
        if self.high_raw < max(self.open_raw, self.close_raw):
            raise ValueError("high_raw cannot be below open_raw or close_raw")
        if self.low_raw > self.high_raw:
            raise ValueError("low_raw cannot exceed high_raw")
        if self.volume_split_adjusted < 0:
            raise ValueError("volume_split_adjusted cannot be negative")

    @classmethod
    def from_eodhd_payload(cls, payload: dict[str, Any]) -> Self:
        """Parse one EODHD daily response row into the canonical contract."""
        return cls(
            trading_date=_parse_date(payload["date"], "date"),
            open_raw=_parse_decimal(payload["open"], "open"),
            high_raw=_parse_decimal(payload["high"], "high"),
            low_raw=_parse_decimal(payload["low"], "low"),
            close_raw=_parse_decimal(payload["close"], "close"),
            close_adjusted=_parse_decimal(payload["adjusted_close"], "adjusted_close"),
            volume_split_adjusted=_parse_int(payload["volume"], "volume"),
        )


@dataclass(frozen=True, slots=True)
class InstrumentMapping:
    """Auditable link between a Trading 212 ticker and market-data symbol."""

    trading212_ticker: str
    trading212_isin: str | None
    market_data_provider: str
    provider_symbol: str
    method: MappingMethod
    quote_convention: QuoteConvention
    verified_at: datetime

    def __post_init__(self) -> None:
        _validate_non_empty(self.trading212_ticker, "trading212_ticker")
        _validate_non_empty(self.market_data_provider, "market_data_provider")
        _validate_non_empty(self.provider_symbol, "provider_symbol")
        if self.trading212_isin is not None and not _ISIN.fullmatch(
            self.trading212_isin
        ):
            raise ValueError("trading212_isin must be a valid ISIN or None")
        if self.method is MappingMethod.ISIN and self.trading212_isin is None:
            raise ValueError("an ISIN mapping requires trading212_isin")
        _validate_aware_datetime(self.verified_at, "verified_at")


@dataclass(frozen=True, slots=True)
class DataProvenance:
    """Metadata needed to reproduce and audit one raw provider response."""

    provider: str
    dataset: str
    source_identifier: str
    retrieved_at_utc: datetime
    request_parameters: tuple[tuple[str, str], ...]
    raw_sha256: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        _validate_non_empty(self.provider, "provider")
        _validate_non_empty(self.dataset, "dataset")
        _validate_non_empty(self.source_identifier, "source_identifier")
        _validate_non_empty(self.schema_version, "schema_version")
        _validate_aware_datetime(self.retrieved_at_utc, "retrieved_at_utc")
        if self.retrieved_at_utc.utcoffset() != timedelta(0):
            raise ValueError("retrieved_at_utc must use UTC")
        if not _SHA256.fullmatch(self.raw_sha256):
            raise ValueError("raw_sha256 must be a lowercase SHA-256 hex digest")

        keys: list[str] = []
        for key, _value in self.request_parameters:
            normalized_key = key.strip().lower().replace("-", "_")
            if any(
                fragment in normalized_key for fragment in _SECRET_PARAMETER_FRAGMENTS
            ):
                raise ValueError(f"secret request parameter cannot be recorded: {key}")
            keys.append(normalized_key)
        if len(keys) != len(set(keys)):
            raise ValueError("request parameter names must be unique")


def _validate_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _validate_currency_code(value: str, field_name: str) -> None:
    if not _CURRENCY_CODE.fullmatch(value):
        raise ValueError(f"{field_name} must be a three-letter uppercase code")


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")


def _parse_decimal(value: Any, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field_name} must be a decimal number") from error
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _parse_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be an integer") from error
    if Decimal(str(value)) != parsed:
        raise ValueError(f"{field_name} must be an integer")
    return parsed


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _parse_date(value: Any, field_name: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"{field_name} must use YYYY-MM-DD") from error


def _parse_datetime(value: Any, field_name: str) -> datetime:
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO 8601 datetime") from error
    _validate_aware_datetime(parsed, field_name)
    return parsed
