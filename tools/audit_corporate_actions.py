"""Rebuild seven shareholder-wealth event returns from cached source data only.

No requests or cache fallback are permitted. Missing cached files are errors.
Normal monthly prices already use adjusted returns; each event gross REPLACES
the provider's event gross, so the child distribution is not added twice.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("America/New_York")


def load(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Required offline cache is missing: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def chart(symbol: str, primary_required: bool = False) -> dict:
    inventory_path = ROOT / "data/raw/corporate_actions" / f"{symbol}_full_chart.json"
    inventory = load(inventory_path)["chart"]["result"][0]
    primary_path = ROOT / "data/raw/yahoo_prices" / f"{symbol}_daily_2015-10-01_2026-08-31.json"
    primary = load(primary_path)["chart"]["result"][0] if primary_required or primary_path.exists() else inventory
    if primary["meta"].get("currency") != "USD" or inventory["meta"].get("currency") != "USD":
        raise ValueError(f"{symbol}: currency must be USD")
    if primary["meta"].get("exchangeTimezoneName") != "America/New_York":
        raise ValueError(f"{symbol}: unexpected exchange timezone")
    closes = dict(zip(inventory["timestamp"], inventory["indicators"]["quote"][0]["close"]))
    compared = [abs(value - closes[t]) / max(1.0, abs(value))
                for t, value in zip(primary["timestamp"], primary["indicators"]["quote"][0]["close"])
                if value is not None and closes.get(t) is not None]
    if not compared or max(compared) > 1e-6:
        raise ValueError(f"{symbol}: source/inventory closing-price units disagree")
    rows = {}
    for i, stamp in enumerate(primary["timestamp"]):
        date = datetime.fromtimestamp(stamp, TZ).date().isoformat()
        if date in rows:
            raise ValueError(f"{symbol}: duplicate daily date")
        rows[date] = {"close": primary["indicators"]["quote"][0]["close"][i],
                      "adjclose": primary["indicators"]["adjclose"][0]["adjclose"][i]}
    return {"rows": rows, "events": primary.get("events", {}),
            "splits": inventory.get("events", {}).get("splits", {}).values(),
            "source_price": str((primary_path if primary_path.exists() else inventory_path).relative_to(ROOT)),
            "split_inventory": str(inventory_path.relative_to(ROOT)),
            "crosscheck_max_relative_close_difference": max(compared)}


def observed_close(data: dict, date: str) -> tuple[float, float]:
    close = data["rows"][date]["close"]
    if not isinstance(close, (int, float)) or not math.isfinite(close) or close <= 0:
        raise ValueError(f"Invalid closing quote on {date}")
    future = [s["numerator"] / s["denominator"] for s in data["splits"]
              if datetime.fromtimestamp(s["date"], TZ).date().isoformat() > date]
    product = math.prod(future)
    return close * product, product


def main(out: Path) -> None:
    official = load(ROOT / "data/evidence/corporate_action_official_core.json")
    frozen = load(ROOT / "data/evidence/corporate_action_economic_corrections.json")
    terms = official["events"]
    if len(terms) != 7 or frozen.get("status") != "pass":
        raise ValueError("Expected seven previously audited mandatory distributions")
    symbols = {e["main_symbol"] for e in terms} | {c["symbol"] for e in terms for c in e["children"]}
    parents = {e["main_symbol"] for e in terms}
    charts = {symbol: chart(symbol, primary_required=symbol in parents) for symbol in sorted(symbols)}
    reference = {e["event_id"]: e for e in frozen["events"]}
    if set(reference) != {e["event_id"] for e in terms}:
        raise ValueError("Official/frozen event identities disagree")
    rebuilt = []
    worst = 0.0
    for event in terms:
        date = event["economic_ex_date"]
        parent = charts[event["main_symbol"]]
        previous = max(d for d in parent["rows"] if d < date)
        cash_events = [x for x in parent["events"].get("dividends", {}).values()
                       if datetime.fromtimestamp(x["date"], TZ).date().isoformat() == date]
        if cash_events:
            raise ValueError(f"{event['event_id']}: ordinary cash dividend requires explicit treatment")
        before, before_factor = observed_close(parent, previous)
        after, after_factor = observed_close(parent, date)
        children = {c["symbol"]: observed_close(charts[c["symbol"]], date)[0] for c in event["children"]}
        payoff = event["main_shares_per_old_share"] * after + sum(
            c["shares_per_old_share"] * children[c["symbol"]] for c in event["children"])
        economic = payoff / before
        vendor = parent["rows"][date]["adjclose"] / parent["rows"][previous]["adjclose"]
        multiplier = economic / vendor
        if not all(math.isfinite(x) and x > 0 for x in (economic, vendor, multiplier)):
            raise ValueError("Nonpositive/nonfinite event gross")
        old = reference[event["event_id"]]
        if previous != old["previous_trading_date"] or event["children"] != old["children"]:
            raise ValueError(f"{event['event_id']}: dates or distribution ratios differ")
        comparisons = {"parent_previous_spot_close": before, "parent_event_spot_close": after,
                       "source_yahoo_daily_gross": vendor, "economic_daily_gross": economic,
                       "multiplier": multiplier}
        for key, value in comparisons.items():
            error = abs(value - old[key])
            worst = max(worst, error)
            if not math.isclose(value, old[key], rel_tol=0, abs_tol=1e-12):
                raise ValueError(f"{event['event_id']}: rebuilt {key} does not match accepted event evidence")
        for symbol, value in children.items():
            if not math.isclose(value, old["child_event_spot_closes"][symbol], rel_tol=0, abs_tol=1e-12):
                raise ValueError(f"{event['event_id']}: child quote differs")
        rebuilt.append({"event_id": event["event_id"], "ticker": event["main_symbol"],
                        "event_date": date, "previous_date": previous,
                        "children": event["children"], **comparisons,
                        "child_event_spot_closes": children,
                        "future_split_products": {"parent_before": before_factor, "parent_after": after_factor},
                        "ordinary_cash_dividend_overlap": False})
    receipt = {"schema_version": 1, "status": "pass", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
               "offline": True, "event_count": len(rebuilt), "max_accepted_evidence_difference": worst,
               "method": "Recover event-date quote units using the full cached split inventory; value mandatory child shares at event close and reinvest in continuing parent; replace the vendor event gross exactly once.",
               "events": rebuilt,
               "sources": {symbol: {k: value for k, value in data.items() if k in
                           {"source_price", "split_inventory", "crosscheck_max_relative_close_difference"}}
                           for symbol, data in charts.items()}}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "pass", "events": len(rebuilt), "offline": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "validation/corporate_actions.json")
    args = parser.parse_args()
    main(args.out)
