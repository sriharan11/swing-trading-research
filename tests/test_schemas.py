"""Synthetic tests for the Phase 1 data contracts."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from swing_trading_research.schemas import (
    DailyOhlcvBar,
    DataProvenance,
    InstrumentMapping,
    InstrumentType,
    MappingMethod,
    QuoteConvention,
    Trading212Instrument,
)


def test_parse_trading212_stock_payload() -> None:
    instrument = Trading212Instrument.from_payload(
        {
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
    )

    assert instrument.instrument_type is InstrumentType.STOCK
    assert instrument.max_open_quantity == Decimal("1000.5")
    assert instrument.quote_convention.major_currency == "USD"


def test_gbx_is_converted_to_gbp_explicitly() -> None:
    quote = QuoteConvention.from_code("GBX")

    assert quote.major_currency == "GBP"
    assert quote.units_per_major == Decimal("100")
    assert quote.to_major(Decimal("3650")) == Decimal("36.5")


def test_missing_isin_remains_unmatched_instead_of_being_guessed() -> None:
    instrument = Trading212Instrument.from_payload(
        {
            "addedOn": "2019-08-24T14:15:22Z",
            "currencyCode": "GBP",
            "extendedHours": False,
            "isin": None,
            "maxOpenQuantity": 100,
            "name": "Synthetic Example",
            "shortName": "Example",
            "ticker": "EXAMPLE_GB_EQ",
            "type": "STOCK",
            "workingScheduleId": 2,
        }
    )

    assert instrument.isin is None


def test_parse_eodhd_bar_preserves_adjustment_semantics() -> None:
    bar = DailyOhlcvBar.from_eodhd_payload(
        {
            "date": "2026-11-06",
            "open": 268.0,
            "high": 273.4,
            "low": 266.5,
            "close": 271.2,
            "adjusted_close": 269.75,
            "volume": 51_000_000,
        }
    )

    assert bar.close_raw == Decimal("271.2")
    assert bar.close_adjusted == Decimal("269.75")
    assert bar.volume_split_adjusted == 51_000_000


def test_daily_bar_rejects_impossible_ohlc_relationship() -> None:
    with pytest.raises(ValueError, match="high_raw cannot be below"):
        DailyOhlcvBar.from_eodhd_payload(
            {
                "date": "2026-11-06",
                "open": 100,
                "high": 99,
                "low": 95,
                "close": 98,
                "adjusted_close": 97,
                "volume": 1000,
            }
        )


def test_isin_mapping_requires_an_isin() -> None:
    with pytest.raises(ValueError, match="requires trading212_isin"):
        InstrumentMapping(
            trading212_ticker="AAPL_US_EQ",
            trading212_isin=None,
            market_data_provider="eodhd",
            provider_symbol="AAPL.US",
            method=MappingMethod.ISIN,
            quote_convention=QuoteConvention.from_code("USD"),
            verified_at=datetime(2026, 11, 9, tzinfo=UTC),
        )


def test_provenance_rejects_secret_parameters() -> None:
    with pytest.raises(ValueError, match="secret request parameter"):
        DataProvenance(
            provider="eodhd",
            dataset="daily_ohlcv",
            source_identifier="AAPL.US",
            retrieved_at_utc=datetime(2026, 11, 9, tzinfo=UTC),
            request_parameters=(("api_token", "must-not-be-recorded"),),
            raw_sha256="a" * 64,
        )


def test_provenance_accepts_reproducible_non_secret_metadata() -> None:
    provenance = DataProvenance(
        provider="eodhd",
        dataset="daily_ohlcv",
        source_identifier="AAPL.US",
        retrieved_at_utc=datetime(2026, 11, 9, tzinfo=UTC),
        request_parameters=(
            ("fmt", "json"),
            ("from", "2025-11-09"),
            ("period", "d"),
            ("to", "2026-11-09"),
        ),
        raw_sha256="a" * 64,
    )

    assert provenance.schema_version == "1.0"
