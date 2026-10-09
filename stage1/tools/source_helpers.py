"""Parse saved Yahoo chart responses and French monthly factors.

Source-native observations are retained without forward filling. French
percentages are divided by 100 exactly once; four-digit annual rows are ignored.
"""
from __future__ import annotations
import csv
import io
import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Any
import numpy as np
import pandas as pd

FIELDS = ["Mkt-RF", "SMB", "HML", "RF"]
MISSING_SENTINELS = {Decimal("-99.99"), Decimal("-999")}


def strict_json(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"Non-JSON numeric constant: {value}")
    return json.loads(text, parse_constant=reject_constant)


def chart_result(payload: dict, symbol: str) -> dict:
    chart = payload.get("chart", {})
    if chart.get("error") is not None:
        raise ValueError(f"Yahoo chart error for {symbol}: {chart['error']}")
    results = chart.get("result")
    if not isinstance(results, list) or len(results) != 1:
        raise ValueError(f"Expected one chart result for {symbol}")
    result = results[0]
    if result.get("meta", {}).get("symbol") != symbol:
        raise ValueError(f"Returned symbol differs from requested {symbol}")
    return result


def daily_frame(payload: dict, symbol: str, start: str, end: str) -> tuple[pd.DataFrame, dict]:
    result = chart_result(payload, symbol)
    meta = result.get("meta", {})
    if meta.get("currency") != "USD":
        raise ValueError(f"{symbol} currency is {meta.get('currency')}, expected USD")
    exchange_tz = meta.get("exchangeTimezoneName")
    if exchange_tz != "America/New_York":
        raise ValueError(f"Unexpected exchange timezone for {symbol}: {exchange_tz}")
    timestamps = result.get("timestamp", [])
    if not timestamps:
        raise ValueError(f"No daily timestamps for {symbol}")
    indicators = result.get("indicators", {})
    quotes = indicators.get("quote", [])
    adjusted = indicators.get("adjclose", [])
    if len(quotes) != 1 or len(adjusted) != 1:
        raise ValueError(f"Missing quote or adjusted-close field for {symbol}")
    n = len(timestamps)
    fields = {key: quotes[0].get(key) for key in ("open", "high", "low", "close", "volume")}
    fields["adjclose"] = adjusted[0].get("adjclose")
    if any(not isinstance(values, list) or len(values) != n for values in fields.values()):
        raise ValueError(f"Timestamp/indicator array length mismatch for {symbol}")
    dates = pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(exchange_tz).tz_localize(None).normalize()
    frame = pd.DataFrame(fields, index=dates).apply(pd.to_numeric, errors="raise")
    frame.index.name = "ObservationDate"
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError(f"Duplicate or unordered daily observation date for {symbol}")
    frame = frame.loc[start:end].copy()
    if frame.empty:
        raise ValueError(f"No daily rows in requested range for {symbol}")
    for field in ("open", "high", "low", "close", "adjclose"):
        values = frame[field].dropna().to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError(f"Invalid non-missing {field} values for {symbol}")
    volume = frame.volume.dropna().to_numpy(dtype=float)
    if not np.isfinite(volume).all() or (volume < 0).any():
        raise ValueError(f"Invalid reported volume for {symbol}")
    events = result.get("events", {})
    event_receipt = {}
    for kind in ("dividends", "splits", "capitalGains"):
        entries = []
        for key, value in sorted(events.get(kind, {}).items(), key=lambda pair: int(pair[0])):
            timestamp = value.get("date", int(key))
            event_date = pd.Timestamp(timestamp, unit="s", tz="UTC").tz_convert(exchange_tz).date().isoformat()
            entries.append({"exchange_local_date": event_date, **value})
        event_receipt[kind] = entries
    receipt = {
        "symbol": symbol, "currency": meta["currency"], "exchange_timezone": exchange_tz,
        "instrument_type": meta.get("instrumentType"),
        "exchange_name": meta.get("exchangeName"),
        "daily_rows": len(frame), "daily_first_date": frame.index[0].date().isoformat(),
        "daily_last_date": frame.index[-1].date().isoformat(),
        "daily_missing_by_field": {key: int(frame[key].isna().sum()) for key in frame.columns},
        "quote_close_to_adjusted_close_ratio_first": float(frame.adjclose.iloc[0] / frame.close.iloc[0]) if pd.notna(frame.close.iloc[0]) and pd.notna(frame.adjclose.iloc[0]) else None,
        "quote_close_to_adjusted_close_ratio_last": float(frame.adjclose.iloc[-1] / frame.close.iloc[-1]) if pd.notna(frame.close.iloc[-1]) and pd.notna(frame.adjclose.iloc[-1]) else None,
        "events": event_receipt,
        "event_counts": {key: len(value) for key, value in event_receipt.items()},
        "returned_source_meta": meta,
        "corporate_action_validation": "Events preserved and finite positive prices checked. Every corporate-action adjustment has not been independently reconstructed or certified.",
    }
    return frame, receipt


def monthly_last_rows(frame: pd.DataFrame, symbol: str, months: pd.PeriodIndex) -> pd.DataFrame:
    # tail(1) preserves a missing terminal observation, unlike groupby.last(),
    # which can silently step back to an earlier non-null quote.
    monthly = frame.groupby(frame.index.to_period("M"), sort=True).tail(1).copy()
    monthly["actual_date"] = monthly.index
    monthly.index = monthly.index.to_period("M")
    if monthly.index.has_duplicates or not monthly.index.equals(months):
        raise ValueError(f"Incomplete or duplicate requested price months for {symbol}")
    if monthly[["close", "adjclose"]].isna().any().any():
        missing = monthly.index[monthly[["close", "adjclose"]].isna().any(axis=1)].astype(str).tolist()
        raise ValueError(f"{symbol} missing close on final returned trading row in {missing}; no earlier row substituted")
    return monthly


def number(value: str) -> Decimal:
    parsed = Decimal(value.strip())
    if not parsed.is_finite():
        raise ValueError(f"Non-finite value: {value!r}")
    return parsed


def parse_monthly(text: str) -> tuple[dict[str, dict[str, Decimal]], dict]:
    """Read the first monthly block only; four-digit annual dates are excluded."""
    rows: dict[str, dict[str, Decimal]] = {}
    header_seen = False
    block_ended = False
    annual_rows_excluded = 0
    preamble: list[str] = []
    for cells in csv.reader(io.StringIO(text)):
        stripped = [cell.strip() for cell in cells]
        if not header_seen:
            if stripped == [""] + FIELDS:
                header_seen = True
            elif stripped:
                preamble.append(",".join(cells))
            continue
        key = stripped[0] if stripped else ""
        if re.fullmatch(r"\d{4}", key):
            annual_rows_excluded += 1
        if rows and not re.fullmatch(r"\d{6}", key):
            block_ended = True
        if block_ended or not re.fullmatch(r"\d{6}", key):
            continue
        datetime.strptime(key, "%Y%m")
        if len(stripped) != 5:
            raise ValueError(f"Unexpected monthly schema at {key}: {len(stripped)} fields")
        month = f"{key[:4]}-{key[4:]}"
        if month in rows:
            raise ValueError(f"Duplicate monthly key: {month}")
        published = [number(value) for value in stripped[1:]]
        if any(value in MISSING_SENTINELS for value in published):
            raise ValueError(f"French missing-value sentinel at {month}")
        rows[month] = {field: value / Decimal(100) for field, value in zip(FIELDS, published)}
    if not header_seen or not rows:
        raise ValueError("No monthly Fama/French three-factor block found")
    keys = sorted(rows)
    vintage = re.search(r"created using the (\d{6}) CRSP database", text)
    return rows, {
        "crsp_database_vintage": vintage.group(1) if vintage else None,
        "preamble": preamble,
        "monthly_row_count": len(rows),
        "monthly_first": keys[0],
        "monthly_last": keys[-1],
        "annual_rows_excluded": annual_rows_excluded,
        "raw_unit": "monthly percent",
        "processed_unit": "monthly decimal return",
        "conversion": "published percentage divided by 100 exactly using Decimal",
        "source_fields": FIELDS,
        "source_period_format": "YYYYMM",
        "output_period_format": "YYYY-MM",
    }
