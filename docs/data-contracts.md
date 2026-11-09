# Phase 1 data contracts

The contracts in `swing_trading_research.schemas` define the meaning and
minimum validity of data before network clients or storage formats are added.
All examples in the test suite are synthetic and safe to publish.

## Trading 212 instrument

`Trading212Instrument` mirrors the documented instrument metadata needed to
construct an account-specific, currently buyable universe. The Trading 212
ticker is its broker identifier. ISIN is optional because incomplete provider
metadata must be reported rather than guessed.

The initial research universe will later filter `instrument_type` to `STOCK`.
Other documented types remain representable so an unexpected response is not
silently recast as a stock.

## Quote convention

`QuoteConvention` keeps quote units separate from major currencies:

| Quote unit | Major currency | Units per major |
|------------|----------------|-----------------|
| USD        | USD            | 1               |
| GBP        | GBP            | 1               |
| GBX        | GBP            | 100             |

For example, `3650 GBX` converts explicitly to `36.50 GBP`. No price is
converted merely because an exchange is in the UK.

## Daily OHLCV bar

`DailyOhlcvBar` encodes adjustment semantics in its field names:

- `open_raw`, `high_raw`, `low_raw`, `close_raw`: as-traded prices.
- `close_adjusted`: close adjusted for splits and dividends.
- `volume_split_adjusted`: volume expressed in post-split share units.

The contract rejects non-positive prices, negative volume, and impossible OHLC
relationships. `Decimal` is used instead of binary floating point so parsing
does not introduce avoidable price rounding.

## Instrument mapping

`InstrumentMapping` is the audit record connecting a Trading 212 ticker to a
market-data-provider symbol. Matching methods, in preferred order, are:

1. ISIN.
2. Ticker plus exchange, followed by validation.
3. Explicit manual review.

Company-name-only matching is intentionally not supported. An ISIN mapping
cannot be recorded without an ISIN, and unmatched instruments must remain
visible in a coverage report.

## Provenance

`DataProvenance` records the provider, dataset, source identifier, UTC retrieval
time, non-secret request parameters, raw-response SHA-256 digest, and schema
version. Secret-looking parameter names are rejected so an API token cannot be
written into a provenance file accidentally.

The raw-response hash lets a later run prove exactly which immutable response
was normalized even when a provider revises historical values.
