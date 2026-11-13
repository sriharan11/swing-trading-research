"""Append-only, local storage for original EODHD historical responses."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from swing_trading_research.providers.eodhd import EodhdDailyHistory
from swing_trading_research.schemas import DataProvenance

_SAFE_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9._-]*")


class RawDataIntegrityError(ValueError):
    """A stored response or its provenance has been changed."""


@dataclass(frozen=True, slots=True)
class StoredEodhdHistory:
    """Paths and audit metadata for one captured response."""

    raw_path: Path
    provenance_path: Path
    provenance: DataProvenance


@dataclass(frozen=True, slots=True)
class RawEodhdStore:
    """Preserve original API response bytes alongside non-secret metadata."""

    root: Path

    def save(
        self,
        history: EodhdDailyHistory,
        *,
        retrieved_at_utc: datetime | None = None,
    ) -> StoredEodhdHistory:
        """Write one capture without overwriting any earlier capture."""
        if not _SAFE_SYMBOL.fullmatch(history.symbol):
            raise ValueError("symbol is not safe for a local directory")

        # A fixed allowlist prevents accidental persistence of API credentials.
        parameters = (
            ("from", history.start_date.isoformat()),
            ("to", history.end_date.isoformat()),
            ("period", "d"),
            ("order", "a"),
            ("fmt", "json"),
        )
        if history.request_parameters != parameters:
            raise ValueError("unexpected request parameters; refusing to store them")

        when = retrieved_at_utc if retrieved_at_utc is not None else datetime.now(UTC)
        digest = hashlib.sha256(history.raw_response).hexdigest()
        provenance = DataProvenance(
            provider="eodhd",
            dataset="daily_ohlcv",
            source_identifier=history.symbol,
            retrieved_at_utc=when,
            request_parameters=parameters,
            raw_sha256=digest,
        )

        folder = self.root / "eodhd" / "daily_ohlcv" / history.symbol
        timestamp = when.strftime("%Y%m%dT%H%M%S.%fZ")
        capture_dir = folder / f"{timestamp}_{digest[:16]}"
        folder.mkdir(parents=True, exist_ok=True)

        if capture_dir.exists():
            raise FileExistsError("This raw-data capture already exists")

        manifest = {
            "schema_version": provenance.schema_version,
            "provider": provenance.provider,
            "dataset": provenance.dataset,
            "source_identifier": provenance.source_identifier,
            "retrieved_at_utc": when.isoformat(),
            "request_parameters": dict(parameters),
            "raw_sha256": digest,
            "row_count": len(history.bars),
            "adjustment_policy": {
                "open": "raw",
                "high": "raw",
                "low": "raw",
                "close": "raw",
                "adjusted_close": "adjusted",
                "volume": "split-adjusted",
            },
        }

        # Stage both files together before publishing the capture directory.
        staging_dir = Path(tempfile.mkdtemp(prefix=".pending-", dir=folder))
        try:
            (staging_dir / "response.json").write_bytes(history.raw_response)
            (staging_dir / "provenance.json").write_text(
                json.dumps(manifest, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            if capture_dir.exists():
                raise FileExistsError("This raw-data capture already exists")
            staging_dir.rename(capture_dir)
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)

        return StoredEodhdHistory(
            raw_path=capture_dir / "response.json",
            provenance_path=capture_dir / "provenance.json",
            provenance=provenance,
        )

    @staticmethod
    def read_verified(capture: StoredEodhdHistory) -> bytes:
        """Only return original bytes when the recorded digest still matches."""
        raw_bytes = capture.raw_path.read_bytes()
        try:
            manifest = json.loads(
                capture.provenance_path.read_text(encoding="utf-8")
            )
            recorded_digest = manifest["raw_sha256"]
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise RawDataIntegrityError("Invalid raw-data provenance file") from error

        actual_digest = hashlib.sha256(raw_bytes).hexdigest()
        if (
            actual_digest != recorded_digest
            or recorded_digest != capture.provenance.raw_sha256
        ):
            raise RawDataIntegrityError("Raw response does not match its SHA-256")
        return raw_bytes
