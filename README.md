# Swing Trading Research

A reproducible Python command-line research project for studying daily US and
UK equity data. Phase 1 builds a provenance-aware historical OHLCV pipeline.
It does **not** train a model or provide trading advice.

## Scope

- Markets: US and UK listed equities
- Frequency: daily OHLCV bars
- Future prediction horizon: 10 trading days (not implemented in Phase 1)
- Interface: Python command line first
- Current status: repository scaffold; no market data has been downloaded

## Research principles

1. Preserve the provider response or an immutable raw representation.
2. Keep raw and adjusted price fields distinct.
3. Record data provenance: provider, symbol, exchange, request parameters,
   retrieval time, timezone, currency, unit, and adjustment policy.
4. Treat UK quote units explicitly. London instruments may be quoted in GBX
   (pence) rather than GBP (pounds); the pipeline must never infer a 100:1
   conversion silently.
5. Validate schema, dates, duplicates, missing values, OHLC relationships,
   non-positive prices, and volume before data is accepted.
6. Keep secrets and downloaded/generated artefacts out of Git.
7. Make research runs reproducible from configuration and recorded metadata.

## Repository layout

```text
src/swing_trading_research/  Python package and CLI
tests/                       Automated tests
.env.example                 Credential names only; never real values
pyproject.toml               Project and tool configuration
```

The ignored `data/`, `artifacts/`, `models/`, and `reports/generated/`
directories will hold local or reproducible outputs later.

## Local setup (PowerShell)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.lock
python -m pip install -e . --no-deps
```

If PowerShell blocks activation, you can run the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
```

`requirements-dev.lock` records the exact development-tool versions used by
this checkout. The compatible version ranges remain declared in
`pyproject.toml` for package metadata and deliberate future upgrades.

## Use the CLI

```powershell
swing-research --help
swing-research version
```

## Quality checks

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

## Planned Phase 1 increments

1. Select and document the historical-data provider and its licence/limits.
2. Define the canonical OHLCV and provenance schemas.
3. Download one US and one UK symbol into an immutable raw layer.
4. Normalize without losing raw/adjusted distinctions or UK quote units.
5. Add deterministic quality checks and fixture-based tests.
6. Add repeatable CLI commands and end-to-end documentation.

## Disclaimer

This project is for education and research. It is not financial advice, and
its outputs must not be treated as recommendations to trade.
