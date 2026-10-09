"""Independent offline input and Stage 1 validation against an accepted snapshot.

Imports no production preparation, portfolio, audit, or plotting functions.
Rebuilds monthly inputs directly from source records; uses centered covariance
and Cholesky solves for tangency, and NNLS (not production SLSQP) for long-only.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import nnls

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("America/New_York")
FIELDS = ["Mkt-RF", "SMB", "HML", "RF"]
CHECKS: list[dict] = []


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append({"check": label, "pass": True})


def close(label: str, actual, expected, tolerance: float = 5e-13) -> None:
    a, b = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise AssertionError(f"{label}: shape or finite-value mismatch")
    error = float(np.max(np.abs(a-b))) if a.size else 0.0
    if error > tolerance:
        raise AssertionError(f"{label}: maximum absolute error {error} > {tolerance}")
    CHECKS.append({"check": label, "pass": True, "max_absolute_error": error, "tolerance": tolerance})


def matrix(relative: str) -> pd.DataFrame:
    return pd.read_csv(ROOT / relative, index_col=0, float_precision="round_trip")


def raw_chart(symbol: str, inventory: bool = False) -> dict:
    name = (f"data/raw/corporate_actions/{symbol}_full_chart.json" if inventory else
            f"data/raw/yahoo_prices/{symbol}_daily_2015-10-01_2026-08-31.json")
    data = load(name)["chart"]["result"][0]
    require(data["meta"].get("currency") == "USD", f"{name}: USD")
    rows = {}
    for i, stamp in enumerate(data["timestamp"]):
        day = datetime.fromtimestamp(stamp, TZ).date().isoformat()
        if day in rows:
            raise ValueError(f"Duplicate raw day: {symbol} {day}")
        rows[day] = {"close": data["indicators"]["quote"][0]["close"][i],
                     "adj": data["indicators"]["adjclose"][0]["adjclose"][i]}
    return {"rows": rows, "events": data.get("events", {}), "meta": data["meta"]}


def independent_inputs(config: dict) -> dict:
    tickers = config["primary_universe"]["tickers"]
    months = pd.period_range("2015-10", "2026-08", freq="M").astype(str).tolist()
    quotes = np.empty((len(months), len(tickers)))
    dates = np.empty(quotes.shape, dtype=object)
    charts = {s: raw_chart(s) for s in tickers}
    for j, symbol in enumerate(tickers):
        monthly = {}
        for date, row in sorted(charts[symbol]["rows"].items()):
            if "2015-10-01" <= date <= "2026-08-31":
                monthly[date[:7]] = (date, row)
        require(list(monthly) == months, f"{symbol}: all 131 monthly terminal records")
        for i, month in enumerate(months):
            day, row = monthly[month]
            if row["close"] is None or row["adj"] is None:
                raise ValueError(f"Missing terminal quote: {symbol} {month}; no forward fill")
            quotes[i, j], dates[i, j] = row["adj"], day
    require(np.isfinite(quotes).all() and (quotes > 0).all(), "All source-native monthly prices positive/finite")
    native = quotes[1:] / quotes[:-1] - 1.0
    selected = native.copy()
    teacher = matrix("data/raw/instructor/prices_us_monthly.csv")
    teacher_months = pd.to_datetime(teacher.index).to_period("M").astype(str).tolist()
    require(len(teacher_months) == len(set(teacher_months)), "Instructor month keys unique")
    teacher_values = teacher.to_numpy(dtype=float)
    teacher_returns = teacher_values[1:] / teacher_values[:-1] - 1.0
    teacher_map = {month: i for i, month in enumerate(teacher_months[1:])}
    retained = [s for s in tickers if s in teacher.columns]
    overlap = [m for m in months[1:] if m in teacher_map]
    require(len(retained) == 15 and len(overlap) == 119 and overlap[0] == "2016-10" and overlap[-1] == "2026-08",
            "Instructor priority covers 15 retained stocks and 119 return months")
    for i, month in enumerate(months[1:]):
        if month in teacher_map:
            for symbol in retained:
                selected[i, tickers.index(symbol)] = teacher_returns[teacher_map[month], teacher.columns.get_loc(symbol)]
    official = load("data/evidence/corporate_action_official_core.json")["events"]
    accepted_events = {e["event_id"]: e for e in load("data/evidence/corporate_action_economic_corrections.json")["events"]}
    symbols = {e["main_symbol"] for e in official} | {c["symbol"] for e in official for c in e["children"]}
    full = {s: raw_chart(s, inventory=True) for s in symbols}

    def spot(symbol: str, day: str) -> float:
        # Main quotations come from the exact sample input; only the complete
        # split inventory comes from the longer corporate-action cache.
        price_rows = charts[symbol]["rows"] if symbol in charts else full[symbol]["rows"]
        value = price_rows[day]["close"]
        product = 1.0
        for split in full[symbol]["events"].get("splits", {}).values():
            split_day = datetime.fromtimestamp(split["date"], TZ).date().isoformat()
            if split_day > day:
                product *= split["numerator"] / split["denominator"]
        return value * product

    corrections = []
    for event in official:
        symbol, day = event["main_symbol"], event["economic_ex_date"]
        prev = sorted(d for d in charts[symbol]["rows"] if d < day)[-1]
        cash = [v for v in charts[symbol]["events"].get("dividends", {}).values()
                if datetime.fromtimestamp(v["date"], TZ).date().isoformat() == day]
        require(not cash, f"{event['event_id']}: no ordinary dividend overlap")
        child_cash = sum(c["shares_per_old_share"] * spot(c["symbol"], day) for c in event["children"])
        shareholder_gross = (event["main_shares_per_old_share"] * spot(symbol, day) + child_cash) / spot(symbol, prev)
        adjusted_gross = charts[symbol]["rows"][day]["adj"] / charts[symbol]["rows"][prev]["adj"]
        multiplier = shareholder_gross / adjusted_gross
        old = accepted_events[event["event_id"]]
        close(f"{event['event_id']}: accepted event multiplier", multiplier, old["multiplier"], 1e-12)
        i, j = months[1:].index(day[:7]), tickers.index(symbol)
        ordinary = float(selected[i, j])
        selected[i, j] = (1.0 + native[i, j]) * multiplier - 1.0
        corrections.append([ordinary, native[i, j], selected[i, j], multiplier, (selected[i, j]-ordinary)*1e4])
    require(len(official) == 7 and np.isfinite(selected).all() and (selected > -1).all(), "Seven events and 130x29 finite returns")
    wealth = np.vstack([np.full(len(tickers), 100.0), np.cumprod(1.0+selected, axis=0)*100.0])
    # Parse published monthly rows independently: yearly rows have only 4 digits.
    source_text = (ROOT / "data/raw/french/F-F_Research_Data_Factors.csv").read_text(encoding="utf-8-sig")
    require(bool(re.search(r"created using the 202608 CRSP database", source_text)), "French 202608 frozen release")
    factor_map = {}
    for cells in csv.reader(io.StringIO(source_text)):
        if len(cells) == 5 and re.fullmatch(r"\d{6}", cells[0].strip()):
            key = cells[0].strip()
            values = [Decimal(c.strip()) for c in cells[1:]]
            if any(v in [Decimal("-99.99"), Decimal("-999")] for v in values):
                raise ValueError(f"French {key}: missing-value sentinel")
            month = key[:4] + "-" + key[4:]
            if month in factor_map:
                raise ValueError("Duplicate French month")
            factor_map[month] = [float(v / Decimal(100)) for v in values]
    factors = np.asarray([factor_map[m] for m in months[1:]])
    require(factors.shape == (130,4) and np.isfinite(factors).all(), "130 published French monthly observations converted exactly once")
    caps = []
    for symbol in tickers:
        payload = load(f"data/raw/yahoo_market_caps/{symbol}_monthlyMarketCap_2026-08-31.json")
        matching = [r for item in payload["timeseries"]["result"] if item.get("meta", {}).get("symbol") == [symbol]
                    for r in item.get("monthlyMarketCap", [])
                    if r.get("asOfDate") == "2026-08-31" and r.get("periodType") == "1M" and r.get("currencyCode") == "USD"]
        require(len(matching) == 1, f"{symbol}: one exact 1M/USD sample-end cap")
        caps.append(float(matching[0]["reportedValue"]["raw"]))
    caps = np.asarray(caps)
    require(np.isfinite(caps).all() and (caps > 0).all(), "Positive source-native caps")
    return {"tickers": tickers, "months": months[1:], "price_months": months, "returns": selected,
            "factors": factors, "native": native, "quotes": quotes, "dates": dates,
            "wealth": wealth, "caps": caps, "value_weights": caps/caps.sum(), "corrections": np.asarray(corrections)}


def fit(values: np.ndarray, rf: np.ndarray) -> dict:
    mean = values.mean(axis=0)
    centered = values-mean
    covariance = centered.T @ centered / (len(values)-1)
    premium = mean-rf.mean()
    eig = np.linalg.eigvalsh(covariance)
    require(eig.min() > 0, f"Positive covariance for {len(values)}x{values.shape[1]} fit")
    direction = cho_solve(cho_factor(covariance, lower=True), premium)
    require(direction.sum() > 0, "Positive budget-normalization direction")
    weights = direction/direction.sum()
    return {"weights": weights, "mean": mean, "premium": premium, "covariance": covariance,
            "direction": direction, "minimum_eigenvalue": float(eig.min())}


def statistics(values, rf, weights) -> dict:
    raw = values @ weights
    excess = raw-rf
    raw_vol = np.std(raw, ddof=1)*np.sqrt(12)
    excess_vol = np.std(excess, ddof=1)*np.sqrt(12)
    return {"annual_mean": float(raw.mean()*12), "annual_excess_mean": float(excess.mean()*12),
            "annual_volatility": float(raw_vol), "annual_excess_volatility": float(excess_vol),
            "sharpe_model_annual": float(excess.mean()*12/raw_vol),
            "sharpe_realized_excess_annual": float(excess.mean()*12/excess_vol),
            "min_month": float(raw.min()), "max_month": float(raw.max()),
            "gross_exposure": float(abs(weights).sum()), "short_exposure": float(-weights[weights<0].sum()),
            "maximum_absolute_weight": float(abs(weights).max())}


def long_only(model: dict) -> np.ndarray:
    # Project the whitened premium on the cone L.T*y, y>=0. This solves the
    # positive Sharpe direction independently of production's equality QP.
    lower = np.linalg.cholesky(model["covariance"])
    target = np.linalg.solve(lower, model["premium"])
    direction, _ = nnls(lower.T, target, maxiter=10000)
    require(direction.sum() > 0, "Nonzero NNLS long-only direction")
    gradient = model["covariance"] @ direction-model["premium"]
    active = direction > 1e-9
    require(np.max(abs(gradient[active])) < 1e-10 and (gradient[~active].min() if (~active).any() else 0) >= -1e-10,
            "Independent NNLS long-only KKT conditions")
    return direction/direction.sum()


def main() -> dict:
    config = load("config/universe.json")
    reference = load("validation/accepted_reference.json")
    require(config["analysis_version"] == reference["analysis_version"] == "dow2015_29", "Current 29-stock analysis version")
    require(config["sample"]["return_start_month"] == "2015-11" and config["sample"]["return_end_month"] == "2026-08"
            and config["sample"]["return_months"] == 130 and config["sample"]["value_weight_as_of_date"] == "2026-08-31",
            "Configuration uses the accepted full sample and cap date")
    roster = load("data/evidence/roster_and_removals.json")["roster"]
    expected_tickers = ["RTX" if m["original_ticker"] == "UTX" else m["original_ticker"]
                        for m in roster if m["original_ticker"] != "DD"]
    require(config["primary_universe"]["tickers"] == expected_tickers, "Historical 2015 roster with UTX/RTX and old DuPont exclusion")
    require([(m["original_ticker"],m["later_index_removal_date"]) for m in config["primary_universe"]["members"]]
            == [(m["original_ticker"],m["later_index_removal_date"]) for m in roster], "Configuration removal dates match official roster evidence")
    rebuilt = independent_inputs(config)
    require(len(rebuilt["tickers"]) == 29 and len(rebuilt["months"]) == 130, "Primary universe and sample dimensions")
    for name, fields in [("returns", rebuilt["tickers"]), ("factors", FIELDS)]:
        frozen = reference["inputs"][name]
        require(frozen["months"] == rebuilt["months"] and frozen["columns"] == fields, f"Frozen {name} keys/order")
        close(f"Raw rebuilt {name} versus accepted snapshot", rebuilt[name], frozen["values"], 2e-15)
    close("Raw caps versus accepted snapshot", rebuilt["caps"], reference["inputs"]["caps"]["market_cap"], 0)
    close("Raw value weights versus accepted snapshot", rebuilt["value_weights"], reference["inputs"]["caps"]["value_weight"], 1e-15)
    matrices = {"returns_us_monthly.csv": ("returns", rebuilt["months"], rebuilt["tickers"]),
                "ff3_monthly.csv": ("factors", rebuilt["months"], FIELDS),
                "yahoo_native_returns_monthly.csv": ("native", rebuilt["months"], rebuilt["tickers"]),
                "vendor_adjusted_prices_us_monthly.csv": ("quotes", rebuilt["price_months"], rebuilt["tickers"]),
                "prices_us_monthly.csv": ("wealth", rebuilt["price_months"], rebuilt["tickers"])}
    for filename, (key, months, columns) in matrices.items():
        table = matrix("data/processed/"+filename)
        require(table.index.tolist() == months and table.columns.tolist() == columns and table.index.is_unique,
                filename+": period keys and ticker order")
        close(filename+": independent raw reconstruction", table, rebuilt[key], 1e-10 if key == "wealth" else 2e-15)
    date_table = matrix("data/processed/month_end_observation_dates.csv")
    require(date_table.index.tolist() == rebuilt["price_months"] and date_table.columns.tolist() == rebuilt["tickers"]
            and np.array_equal(date_table.to_numpy(), rebuilt["dates"]), "All Yahoo monthly terminal observation dates")
    cap_table = pd.read_csv(ROOT/"data/processed/market_caps.csv", float_precision="round_trip")
    weight_table = pd.read_csv(ROOT/"data/processed/value_weights.csv", float_precision="round_trip")
    for filename, table in [("market_caps", cap_table), ("value_weights", weight_table)]:
        require(table.ticker.tolist() == rebuilt["tickers"] and set(table.as_of_date) == {"2026-08-31"}
                and set(table.currency) == {"USD"}, filename+": identity/date/currency")
        close(filename+": raw cap values", table.market_cap, rebuilt["caps"], 0)
    require(set(cap_table.field) == {"monthlyMarketCap"} and set(cap_table.period_type) == {"1M"}, "Processed cap field and period metadata")
    close("Normalized static value weights", weight_table.value_weight, rebuilt["value_weights"], 1e-15)
    correction_table = pd.read_csv(ROOT/"data/processed/corporate_action_return_corrections.csv", float_precision="round_trip")
    terms = load("data/evidence/corporate_action_official_core.json")["events"]
    require(correction_table.ticker.tolist() == [e["main_symbol"] for e in terms]
            and correction_table.event_date.tolist() == [e["economic_ex_date"] for e in terms]
            and correction_table.month.tolist() == [e["economic_ex_date"][:7] for e in terms], "Processed event identity/date order")
    close("Seven processed event-month corrections", correction_table[["ordinary_selected_return", "yahoo_native_return",
          "corrected_return", "multiplier", "change_bp"]], rebuilt["corrections"], 1e-9)
    R, rf = rebuilt["returns"], rebuilt["factors"][:,3]
    slices = {"full_sample": slice(None), "first_half": slice(0,65), "second_half": slice(65,None)}
    models = {name: fit(R[part], rf[part]) for name, part in slices.items()}
    production = load("results/stage1/results.json")
    for name, model in models.items():
        expected = reference["models"][name]
        close(name+": Cholesky versus frozen tangency weights", model["weights"], expected["weights"], 2e-12)
        close(name+": production tangency weights", production["models"][name]["weights"], model["weights"], 2e-12)
        close(name+": production mean/covariance", production["models"][name]["covariance_monthly"], model["covariance"], 2e-15)
    nnls_weights = long_only(models["full_sample"])
    close("NNLS versus accepted SLSQP long-only weights", nnls_weights, reference["long_only"]["weights"], 1e-6)
    close("Production versus accepted long-only weights", production["long_only"]["weights"], reference["long_only"]["weights"], 1e-6)
    require(int((nnls_weights > 1e-7).sum()) == 9, "Long-only nine positive holdings")
    portfolios = {"Tangency (full sample)": models["full_sample"]["weights"],
                  "Value weighted (2026-08-31)": rebuilt["value_weights"],
                  "Long-only tangency (full sample)": nnls_weights,
                  "Tangency (first half)": models["first_half"]["weights"],
                  "Tangency (second half)": models["second_half"]["weights"]}
    stats_table = pd.read_csv(ROOT/"results/stage1/portfolio_statistics.csv", float_precision="round_trip")
    for row in reference["portfolio_statistics"]:
        name, window = row["portfolio"], row["evaluation_window"]
        part = slices[window]
        independent = statistics(R[part], rf[part], portfolios[name])
        table_rows = stats_table[(stats_table.portfolio == name) & (stats_table.evaluation_window == window)]
        require(len(table_rows) == 1, f"Statistics row {name}/{window}")
        for key, value in independent.items():
            tolerance = 1e-6 if name.startswith("Long-only") else 2e-12
            close(f"Accepted statistic {name}/{window}/{key}", value, row[key], tolerance)
            close(f"Production statistic {name}/{window}/{key}", table_rows.iloc[0][key], value, tolerance)
    series_table = matrix("results/stage1/portfolio_monthly_returns.csv")
    require(series_table.index.tolist() == rebuilt["months"] and series_table.columns.tolist() == list(portfolios), "Portfolio monthly return keys")
    for name, weights in portfolios.items():
        close(name+": monthly target-weight return series", series_table[name], R@weights,
              1e-7 if name.startswith("Long-only") else 2e-13)
    summary = pd.read_csv(ROOT/"results/stage1/exhibit_1a_summary_stats.csv", float_precision="round_trip")
    require(summary.ticker.tolist() == rebuilt["tickers"] and (summary.observations == 130).all(), "Summary ticker order and observation count")
    close("Summary monthly means", summary.mean_monthly, R.mean(axis=0), 2e-15)
    close("Summary monthly volatility", summary.volatility_monthly, np.std(R,axis=0,ddof=1), 2e-15)
    close("Estimated covariance CSV", matrix("results/stage1/estimated_covariance_monthly.csv"), models["full_sample"]["covariance"], 2e-15)
    means_table = pd.read_csv(ROOT/"results/stage1/estimated_mean_vectors.csv", float_precision="round_trip")
    require(means_table.ticker.tolist() == rebuilt["tickers"], "Estimated mean-vector ticker order")
    close("Estimated raw mean vector CSV", means_table.mean_monthly, models["full_sample"]["mean"], 2e-15)
    close("Estimated excess mean vector CSV", means_table.excess_mean_monthly, models["full_sample"]["premium"], 2e-15)
    output_weights = pd.read_csv(ROOT/"results/stage1/exhibit_1b_weights.csv", float_precision="round_trip")
    close("Exhibit 1b unrestricted weights", output_weights.tangency_weight, models["full_sample"]["weights"], 2e-12)
    close("Exhibit 1b value weights", output_weights.value_weight, rebuilt["value_weights"], 1e-15)
    close("Exhibit 1b long-only weights", output_weights.long_only_weight, nnls_weights, 1e-6)
    drift_table = pd.read_csv(ROOT/"results/stage1/exhibit_1c_subsample_weights.csv", float_precision="round_trip")
    require(drift_table.ticker.tolist() == rebuilt["tickers"], "Three-series time-chart ticker order")
    for name, column in [("full_sample","full_sample_weight"),("first_half","first_half_weight"),("second_half","second_half_weight")]:
        close("Time-chart "+column, drift_table[column], models[name]["weights"], 2e-12)
    members = config["primary_universe"]["members"]
    removed = {m["quote_symbol"] for m in members if m["included"] and m.get("later_index_removal_date")
               and m["later_index_removal_date"] <= "2026-08-31"}
    require(removed == {"GE","XOM","PFE","RTX","INTC","VZ"}, "Six later DJIA removals retained")
    mask23 = np.array([s not in removed for s in rebuilt["tickers"]])
    masks = {"all_29": np.ones(29,dtype=bool), "retained_23": mask23, "later_removals_6": ~mask23}
    sensitivity = load("results/stage1/universe_sensitivity/results.json")
    sensitivity_weights = pd.read_csv(ROOT/"results/stage1/universe_sensitivity/weights.csv", float_precision="round_trip")
    sensitivity_statistics = pd.read_csv(ROOT/"results/stage1/universe_sensitivity/portfolio_statistics.csv", float_precision="round_trip")
    sensitivity_series = matrix("results/stage1/universe_sensitivity/portfolio_monthly_returns.csv")
    require(sensitivity_weights.ticker.tolist() == rebuilt["tickers"] and
            sensitivity_weights.included_in_23.tolist() == mask23.tolist(), "Universe chart eligibility and ticker order")
    require(sensitivity_series.index.tolist() == rebuilt["months"], "Universe monthly portfolio date keys")
    labels = {"all_29":"All 29 tangency", "retained_23":"Retained 23 tangency", "later_removals_6":"Later-removal 6 tangency"}
    columns = {"all_29":"weight_29", "retained_23":"weight_23", "later_removals_6":"weight_6"}
    universe_stats = {}
    for name, mask in masks.items():
        independent = fit(R[:,mask], rf)
        accepted = reference["universe_models"][name]
        close(name+": accepted subset weights", independent["weights"], accepted["weights"], 2e-12)
        close(name+": production subset weights", sensitivity["models"][name]["weights"], independent["weights"], 2e-12)
        close(name+": universe chart CSV weights", sensitivity_weights.loc[mask,columns[name]], independent["weights"], 2e-12)
        if (~mask).any():
            require(sensitivity_weights.loc[~mask,columns[name]].isna().all(), name+": ineligible weights remain missing rather than estimated zeros")
        close(name+": universe portfolio CSV series", sensitivity_series[labels[name]], R[:,mask]@independent["weights"], 2e-13)
        stats = statistics(R[:,mask], rf, independent["weights"])
        universe_stats[name] = stats
        reported = sensitivity_statistics[sensitivity_statistics.portfolio == labels[name]]
        require(len(reported) == 1 and int(reported.iloc[0].assets) == int(mask.sum()), name+": subset performance-table identity")
        for key, accepted_key in [("annual_mean","annual_mean"),("annual_volatility","annual_volatility"),
                                  ("sharpe_model_annual","model_sharpe_annual"),("gross_exposure","gross_exposure")]:
            close(name+": accepted subset "+key, stats[key], accepted[accepted_key], 2e-12)
            close(name+": subset performance CSV "+key, stats[key], reported.iloc[0][accepted_key], 2e-12)
    baseline = universe_stats["all_29"]["sharpe_model_annual"]
    require(baseline >= universe_stats["retained_23"]["sharpe_model_annual"]-1e-10 and
            baseline >= universe_stats["later_removals_6"]["sharpe_model_annual"]-1e-10, "Nested-universe maximum Sharpe ordering")
    first, second = models["first_half"]["weights"], models["second_half"]["weights"]
    require(int(((first*second)<0).sum()) == 17, "17 first/second holding sign changes")
    close("First/second weight correlation", np.corrcoef(first,second)[0,1], reference["stability"]["first_second_weight_correlation"], 2e-12)
    display_stats = {"full_tangency": statistics(R,rf,portfolios["Tangency (full sample)"]),
                     "value_weighted": statistics(R,rf,rebuilt["value_weights"]),
                     "long_only": statistics(R,rf,nnls_weights),
                     "first_half": statistics(R[:65],rf[:65],first), "second_half": statistics(R[65:],rf[65:],second),
                     "retained_23": universe_stats["retained_23"], "later_removals_6": universe_stats["later_removals_6"]}
    for name, stats in display_stats.items():
        displayed = {"annual_mean_pct": round(stats["annual_mean"]*100,3),
                     "annual_volatility_pct": round(stats["annual_volatility"]*100,3),
                     "model_sharpe": round(stats["sharpe_model_annual"],3), "gross_pct": round(stats["gross_exposure"]*100,3)}
        require(displayed == reference["report_display"][name], name+": latest report three-decimal values")
    return {"schema_version":1, "status":"pass", "analysis_version":"dow2015_29",
            "checked_at_utc":datetime.now(timezone.utc).isoformat(), "offline":True,
            "methods":{"source_inputs":"Independent source JSON/CSV parsing, instructor ordinary-month priority, event-date wealth reconstruction and exact cap-date selection",
                       "unrestricted":"Centered sample covariance and independent Cholesky solve",
                       "long_only":"Whitened-premium NNLS projection plus KKT verification; production uses SLSQP",
                       "baseline":"Frozen pre-packaging accepted_reference.json; never regenerated by production pipeline"},
            "assets":29, "monthly_returns":130, "event_count":7, "checks":CHECKS,
            "limits":["Numerical reproduction verifies the accepted source snapshot and methodology, not all provider adjustments or original publication-time vintages.",
                      "Report Word/PDF prose and layout are independently edited artifacts and are not regenerated by this numerical validator."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT/"validation/reproduction.json")
    args = parser.parse_args()
    try:
        receipt = main()
    except Exception as exc:
        receipt = {"status":"failed", "offline":True, "error_type":type(exc).__name__, "error":str(exc), "checks":CHECKS}
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(receipt,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        raise
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(receipt,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":receipt["status"], "checks":len(CHECKS), "assets":29, "months":130, "offline":True}))
