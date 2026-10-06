"""Rebuild the accepted 29-stock inputs offline from frozen source snapshots.

Teacher prices have priority on covered ordinary months. Seven mandatory
distributions replace the event-day provider gross return. Linked prices are
baseline-100 wealth indices, while native provider quote prices remain separate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
from source_helpers import daily_frame, monthly_last_rows, parse_monthly, strict_json

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
EVIDENCE = ROOT / "data/evidence"
TICKERS = "MMM AXP AAPL BA CAT CVX CSCO KO XOM GE GS HD INTC IBM JNJ JPM MCD MRK MSFT NKE PFE PG TRV RTX UNH VZ V WMT DIS".split()
CAP_SOURCE = "yahoo_finance_monthly_marketcap_20260831_20261006"


def save(frame: pd.DataFrame, path: Path, index: bool = True) -> None:
    frame.to_csv(path, index=index, float_format="%.17g")
    back = pd.read_csv(path, index_col=0 if index else None, float_precision="round_trip")
    columns = frame.select_dtypes(include=[np.number]).columns
    assert np.array_equal(back[columns].to_numpy(), frame[columns].to_numpy())


def native_cap(symbol: str) -> dict:
    raw = RAW / "yahoo_market_caps" / f"{symbol}_monthlyMarketCap_2026-08-31.json"
    meta = raw.with_name(raw.stem + ".metadata.json")
    payload = strict_json(raw.read_text(encoding="utf-8"))
    metadata = strict_json(meta.read_text(encoding="utf-8"))
    assert payload["timeseries"].get("error") is None
    selected = [row for series in payload["timeseries"]["result"]
                if series.get("meta", {}).get("symbol") == [symbol]
                and series.get("meta", {}).get("type") == ["monthlyMarketCap"]
                for row in series.get("monthlyMarketCap", [])
                if row["asOfDate"] == "2026-08-31" and row["periodType"] == "1M"
                and row["currencyCode"] == "USD"]
    assert len(selected) == 1 and metadata["symbol"] == symbol
    value = float(selected[0]["reportedValue"]["raw"])
    assert np.isfinite(value) and value > 0
    return {"ticker": symbol, "provider_symbol": symbol, "as_of_date": "2026-08-31",
            "currency": "USD", "market_cap": value, "field": "monthlyMarketCap",
            "period_type": "1M", "provider": "Yahoo Finance", "source": CAP_SOURCE,
            "share_scope": "provider_reported_company_equity_market_cap",
            "source_raw": raw.relative_to(ROOT).as_posix(),
            "source_metadata": meta.relative_to(ROOT).as_posix(),
            "fetched_at_utc": metadata.get("received_at_utc"),
            "endpoint": metadata["endpoint"],
            "scope_limit": "Native provider value; daily share ledger and exact multiclass valuation formula not independently certified."}


def rebuild(out: Path, action_file: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / "config/universe.json").read_text(encoding="utf-8"))
    roster = json.loads((EVIDENCE / "roster_and_removals.json").read_text(encoding="utf-8"))
    assert config["primary_universe"]["tickers"] == TICKERS
    roster_tickers = ["RTX" if row["original_ticker"] == "UTX" else row["original_ticker"]
                      for row in roster["roster"] if row["original_ticker"] != "DD"]
    assert roster_tickers == TICKERS
    periods = pd.period_range("2015-10", "2026-08", freq="M")
    calendar = periods.astype(str).tolist()
    prices = pd.DataFrame(index=calendar, columns=TICKERS, dtype=float)
    dates = pd.DataFrame(index=calendar, columns=TICKERS, dtype=str)
    for symbol in TICKERS:
        path = RAW / "yahoo_prices" / f"{symbol}_daily_2015-10-01_2026-08-31.json"
        payload = strict_json(path.read_text(encoding="utf-8"))
        daily, _ = daily_frame(payload, symbol, "2015-10-01", "2026-08-31")
        monthly = monthly_last_rows(daily, symbol, periods)
        prices[symbol] = monthly.adjclose.to_numpy()
        dates[symbol] = monthly.actual_date.dt.strftime("%Y-%m-%d").to_numpy()
    prices.index.name = dates.index.name = "Month"
    assert prices.shape == (131, 29) and not dates.isna().any().any()
    assert np.isfinite(prices.to_numpy()).all() and (prices.to_numpy() > 0).all()
    native = prices.pct_change(fill_method=None).iloc[1:]
    returns = native.copy()
    teacher_path = RAW / "instructor/prices_us_monthly.csv"
    teacher = pd.read_csv(teacher_path, index_col=0, float_precision="round_trip")
    teacher.index = pd.to_datetime(teacher.index).to_period("M").astype(str)
    assert teacher.index.is_unique
    teacher_returns = teacher.pct_change(fill_method=None).iloc[1:]
    retained = [symbol for symbol in TICKERS if symbol in teacher_returns.columns]
    overlap = [month for month in returns.index if month in teacher_returns.index]
    assert teacher_returns.loc[overlap, retained].notna().all().all()
    returns.loc[overlap, retained] = teacher_returns.loc[overlap, retained]
    difference = native.loc[overlap, retained] - teacher_returns.loc[overlap, retained]
    actions = json.loads(action_file.read_text(encoding="utf-8"))
    assert actions["status"] == "pass"
    corrected = []
    for event in actions["events"]:
        symbol, date = event["main_symbol"], event["economic_ex_date"]
        month, multiplier = date[:7], float(event["multiplier"])
        assert symbol in TICKERS and month in returns.index and np.isfinite(multiplier) and multiplier > 0
        uncorrected = float(returns.at[month, symbol])
        returns.at[month, symbol] = (1 + native.at[month, symbol]) * multiplier - 1
        corrected.append({"ticker": symbol, "month": month, "event_date": date,
                          "ordinary_selected_return": uncorrected,
                          "yahoo_native_return": float(native.at[month, symbol]),
                          "corrected_return": float(returns.at[month, symbol]),
                          "multiplier": multiplier,
                          "change_bp": float((returns.at[month, symbol] - uncorrected) * 1e4)})
    assert len(corrected) == len({(row["ticker"], row["month"]) for row in corrected}) == 7
    assert returns.shape == (130, 29) and np.isfinite(returns.to_numpy()).all() and (returns.to_numpy() > -1).all()
    wealth = pd.concat([pd.DataFrame([np.full(29, 100.)], columns=TICKERS, index=["2015-10"]),
                        (1 + returns).cumprod() * 100])
    wealth.index.name = returns.index.name = "Month"
    reconstruction_error = np.max(abs(wealth.pct_change(fill_method=None).iloc[1:].to_numpy() - returns.to_numpy()))
    assert reconstruction_error < 1e-14
    monthly, info = parse_monthly((RAW / "french/F-F_Research_Data_Factors.csv").read_text(encoding="utf-8-sig"))
    factors = pd.DataFrame([{field: float(monthly[month][field]) for field in ["Mkt-RF", "SMB", "HML", "RF"]}
                            for month in returns.index], index=returns.index)
    factors.index.name = "Month"
    assert factors.shape == (130, 4) and info["crsp_database_vintage"] == "202608"
    caps = pd.DataFrame([native_cap(symbol) for symbol in TICKERS])
    weights = caps[["ticker", "as_of_date", "market_cap", "currency", "share_scope", "source"]].copy()
    weights["value_weight"] = weights.market_cap / weights.market_cap.sum()
    assert abs(weights.value_weight.sum() - 1) < 1e-14
    save(wealth, out / "prices_us_monthly.csv")
    save(returns, out / "returns_us_monthly.csv")
    save(factors, out / "ff3_monthly.csv")
    save(prices, out / "vendor_adjusted_prices_us_monthly.csv")
    dates.to_csv(out / "month_end_observation_dates.csv")
    save(native, out / "yahoo_native_returns_monthly.csv")
    save(caps, out / "market_caps.csv", False)
    save(weights, out / "value_weights.csv", False)
    save(pd.DataFrame(corrected), out / "corporate_action_return_corrections.csv", False)
    receipt = {"status": "inputs_rebuilt_requires_independent_validation",
               "checked_at_utc": datetime.now(timezone.utc).isoformat(),
               "analysis_version": "dow2015_29", "asset_count": 29, "return_months": 130,
               "network_requests": 0, "input_source": "frozen source snapshots",
               "teacher_price_file": teacher_path.relative_to(ROOT).as_posix(),
               "teacher_overlap": {"stocks": retained, "months": len(overlap),
                                   "start": overlap[0], "end": overlap[-1],
                                   "maximum_yahoo_teacher_return_difference_bp": float(abs(difference.to_numpy()).max() * 1e4)},
               "corporate_action_events": 7, "zero_missing_returns": True,
               "french_vintage": info["crsp_database_vintage"], "caps_date": "2026-08-31",
               "wealth_index_reconstruction_max_error": float(reconstruction_error),
               "output": out.relative_to(ROOT).as_posix() if out.is_relative_to(ROOT) else str(out)}
    validation = ROOT / "validation"
    validation.mkdir(exist_ok=True)
    (validation / "input_preparation.json").write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "data/processed")
    parser.add_argument("--actions", type=Path, default=EVIDENCE / "corporate_action_economic_corrections.json")
    args = parser.parse_args()
    receipt = rebuild(args.out.resolve(), args.actions.resolve())
    print(json.dumps({key: receipt[key] for key in ("status", "asset_count", "return_months", "network_requests")}))
