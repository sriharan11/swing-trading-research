"""Offline tests for append-only EODHD response storage."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from swing_trading_research.providers.eodhd import EodhdDailyHistory
from swing_trading_research.schemas import DailyOhlcvBar
from swing_trading_research.storage.raw import RawDataIntegrityError, RawEodhdStore

_CAPTURED_AT = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)


def _history(symbol: str = "AAPL.US", raw: bytes | None = None) -> EodhdDailyHistory:
    payload = [
        {
            "date": "2026-11-09",
            "open": 100,
            "high": 102,
            "low": 99,
            "close": 101,
            "adjusted_close": 100.5,
            "volume": 1234,
        }
    ]
    original = raw if raw is not None else json.dumps(payload).encode("utf-8")
    return EodhdDailyHistory(
        symbol=symbol,
        start_date=date(2026, 11, 9),
        end_date=date(2026, 11, 9),
        raw_response=original,
        bars=(DailyOhlcvBar.from_eodhd_payload(payload[0]),),
        request_parameters=(
            ("from", "2026-11-09"),
            ("to", "2026-11-09"),
            ("period", "d"),
            ("order", "a"),
            ("fmt", "json"),
        ),
    )


@pytest.mark.parametrize("symbol", ["AAPL.US", "BP.LSE"])
def test_saves_original_bytes_with_secret_free_provenance(tmp_path, symbol) -> None:
    history = _history(symbol)
    store = RawEodhdStore(tmp_path / "data" / "raw")

    capture = store.save(history, retrieved_at_utc=_CAPTURED_AT)

    assert capture.raw_path.read_bytes() == history.raw_response
    assert capture.raw_path.parent == capture.provenance_path.parent
    assert symbol in capture.raw_path.parts
    assert store.read_verified(capture) == history.raw_response
    assert (
        capture.provenance.raw_sha256
        == hashlib.sha256(history.raw_response).hexdigest()
    )

    manifest_text = capture.provenance_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert manifest["source_identifier"] == symbol
    assert manifest["row_count"] == 1
    assert manifest["adjustment_policy"]["adjusted_close"] == "adjusted"
    assert manifest["request_parameters"]["fmt"] == "json"
    assert "api_token" not in manifest_text
    assert "api_key" not in manifest_text


def test_repeated_capture_cannot_overwrite_existing_files(tmp_path) -> None:
    store = RawEodhdStore(tmp_path)
    history = _history()
    first = store.save(history, retrieved_at_utc=_CAPTURED_AT)

    with pytest.raises(FileExistsError, match="already exists"):
        store.save(history, retrieved_at_utc=_CAPTURED_AT)

    assert first.raw_path.read_bytes() == history.raw_response


def test_different_responses_keep_separate_captures(tmp_path) -> None:
    store = RawEodhdStore(tmp_path)
    first = store.save(_history(), retrieved_at_utc=_CAPTURED_AT)
    second = store.save(
        _history(raw=b'[{"provider":"revised"}]'),
        retrieved_at_utc=_CAPTURED_AT,
    )

    assert first.raw_path != second.raw_path
    assert first.raw_path.read_bytes() != second.raw_path.read_bytes()


def test_rejects_unapproved_parameters(tmp_path) -> None:
    history = replace(
        _history(),
        request_parameters=(("api_token", "private-value"),),
    )

    with pytest.raises(ValueError, match="unexpected request parameters"):
        RawEodhdStore(tmp_path).save(history, retrieved_at_utc=_CAPTURED_AT)
    assert not list(tmp_path.iterdir())


def test_rejects_unsafe_symbol(tmp_path) -> None:
    history = replace(_history(), symbol="../private")

    with pytest.raises(ValueError, match="not safe"):
        RawEodhdStore(tmp_path).save(history, retrieved_at_utc=_CAPTURED_AT)


def test_rejects_naive_timestamps(tmp_path) -> None:
    naive_time = datetime(2026, 11, 13, 10, 0)

    with pytest.raises(ValueError, match="must include a timezone"):
        RawEodhdStore(tmp_path).save(_history(), retrieved_at_utc=naive_time)


def test_detects_modified_response(tmp_path) -> None:
    store = RawEodhdStore(tmp_path)
    capture = store.save(_history(), retrieved_at_utc=_CAPTURED_AT)
    capture.raw_path.write_bytes(b"tampered")

    with pytest.raises(RawDataIntegrityError, match="does not match"):
        store.read_verified(capture)


def test_detects_modified_manifest_digest(tmp_path) -> None:
    store = RawEodhdStore(tmp_path)
    capture = store.save(_history(), retrieved_at_utc=_CAPTURED_AT)
    manifest = json.loads(capture.provenance_path.read_text(encoding="utf-8"))
    manifest["raw_sha256"] = "0" * 64
    capture.provenance_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RawDataIntegrityError, match="does not match"):
        store.read_verified(capture)
