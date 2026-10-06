"""Optionally fetch a new public-source snapshot into a NEW directory.

The approved offline snapshot is never refreshed or overwritten. Requests use
the endpoints and parameters recorded in the frozen public-source metadata.
French's official URL provides its currently published vintage. A fresh
snapshot may revise historical adjusted prices and requires separate review.
No authentication, credentials, cookies or personal database are required.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import zipfile

import requests
from source_helpers import parse_monthly, strict_json

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "data/raw"
FRENCH_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip"
SCOPES = ["prices", "caps", "actions", "french"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def get(url: str, params: dict) -> tuple[bytes, dict]:
    requested_at = now()
    response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"},
                            timeout=35, allow_redirects=True)
    metadata = {"endpoint": url, "requested_parameters": params,
                "requested_at_utc": requested_at, "received_at_utc": now(),
                "authentication": "none", "http_status": response.status_code,
                "final_url": response.url,
                "response_date_header": response.headers.get("Date"),
                "response_content_type": response.headers.get("Content-Type")}
    response.raise_for_status()  # Includes 429: no retry or next request.
    return response.content, metadata


def fetch_group(scope: str, output: Path) -> list[dict]:
    mapping = {"prices": ("yahoo_prices", "*.metadata.json"),
               "caps": ("yahoo_market_caps", "*.metadata.json"),
               "actions": ("corporate_actions", "*_request.json")}
    directory, pattern = mapping[scope]
    sources = sorted((FROZEN / directory).glob(pattern))
    if not sources:
        raise FileNotFoundError("Frozen request metadata missing for " + scope)
    target = output / directory
    target.mkdir()
    records = []
    for source in sources:
        original = strict_json(source.read_text(encoding="utf-8"))
        symbol = original["symbol"]
        params = original.get("requested_parameters", original.get("params"))
        if not isinstance(params, dict):
            raise ValueError("Request parameters missing: " + source.name)
        endpoint = original["endpoint"]
        expected_endpoint = (f"https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}"
                             if scope == "caps" else f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}")
        if endpoint != expected_endpoint:
            raise ValueError("Unexpected public endpoint in " + source.name)
        body, metadata = get(endpoint, params)
        payload = strict_json(body.decode("utf-8"))
        field = "timeseries" if scope == "caps" else "chart"
        if payload.get(field, {}).get("error") is not None or not payload.get(field, {}).get("result"):
            raise ValueError(f"Source returned an error or empty response for {symbol}")
        raw_name = (symbol + "_full_chart.json" if scope == "actions"
                    else source.name.replace(".metadata.json", ".json"))
        raw = target / raw_name
        raw.write_bytes(body)
        metadata.update({"provider": "Yahoo Finance", "symbol": symbol,
                         "raw_response_file": raw.relative_to(output).as_posix(),
                         "copied_request_from": source.relative_to(ROOT).as_posix(),
                         "frozen_original_retrieved_at_utc": original.get("received_at_utc", original.get("retrieved_at_utc", original.get("retrieved_at")))})
        for key in ("requested_start_date", "requested_end_date_inclusive", "target_as_of_date"):
            if key in original:
                metadata[key] = original[key]
        if scope == "actions":
            metadata["params"] = params
            metadata["retrieved_at"] = metadata["received_at_utc"]
        dump(target / source.name, metadata)
        records.append({"scope": scope, "symbol": symbol, "file": raw.relative_to(output).as_posix(),
                        "http_status": metadata["http_status"], "bytes": len(body)})
        print(json.dumps(records[-1]), flush=True)
    return records


def fetch_french(output: Path) -> dict:
    directory = output / "french"
    directory.mkdir()
    body, metadata = get(FRENCH_URL, {})
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError("Expected one French CSV in official archive")
        csv_bytes = archive.read(names[0])
    _, info = parse_monthly(csv_bytes.decode("utf-8-sig"))
    (directory / "F-F_Research_Data_Factors_CSV.zip").write_bytes(body)
    (directory / "F-F_Research_Data_Factors.csv").write_bytes(csv_bytes)
    metadata.update({"provider": "Kenneth R. French Data Library", "parsed": info})
    dump(directory / "metadata.json", metadata)
    return {"scope": "french", "vintage": info["crsp_database_vintage"],
            "latest_month": info["monthly_last"], "http_status": metadata["http_status"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path,
                        help="New snapshot directory; must not already exist or be inside data/raw")
    parser.add_argument("--scope", choices=["all", *SCOPES], default="all")
    args = parser.parse_args()
    target, frozen = args.output.expanduser().resolve(), FROZEN.resolve()
    if target == frozen or target.is_relative_to(frozen):
        parser.error("The frozen data/raw directory and its children cannot be written")
    if target.exists():
        parser.error("Output must be a new directory; existing data are never overwritten")
    target.mkdir(parents=True)
    receipt = {"status": "started", "started_at_utc": now(), "scope": args.scope,
               "frozen_snapshot_modified": False, "records": [],
               "note": "New source vintage only; no accepted project data or results replaced."}
    dump(target / "collection_receipt.json", receipt)
    try:
        for scope in SCOPES if args.scope == "all" else [args.scope]:
            if scope == "french":
                receipt["records"].append(fetch_french(target))
            else:
                receipt["records"].extend(fetch_group(scope, target))
            dump(target / "collection_receipt.json", receipt)
        receipt["status"] = "new_snapshot_downloaded_requires_review"
    except Exception as error:
        receipt.update({"status": "partial_fetch_stopped", "error_type": type(error).__name__,
                        "error": str(error), "retry_performed": False})
        raise
    finally:
        receipt["finished_at_utc"] = now()
        dump(target / "collection_receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "output": str(target)}))


if __name__ == "__main__":
    main()
