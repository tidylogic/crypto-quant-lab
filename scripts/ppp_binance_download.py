#!/usr/bin/env python3
"""Collect checksum-verified Binance USD-M 1m reference candles (never MEXC).

Default CSVs include April 1 warmup. The six-month evaluation window starts
April 13 at 15:00 UTC and ends October 13 at 15:00 UTC, exclusively.
Requires requests; raw responses and candles stay in ignored user_data/data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ARCHIVES = "https://data.binance.vision/data/futures/um"
API = "https://fapi.binance.com/fapi/v1/klines"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "user_data/data/ppp-binance"


def utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Dates require an explicit timezone")
    seconds = parsed.timestamp()
    if seconds % 60:
        raise ValueError("Dates must align to whole minutes")
    return int(seconds)


def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse_kline(row):
    opened = int(row[0])
    closed = int(row[6])
    if not 1_000_000_000_000 <= opened < 10_000_000_000_000:
        raise ValueError(f"Expected futures millisecond timestamps: {opened}")
    if opened % 60_000 or closed != opened + 59_999:
        raise ValueError(f"Invalid minute alignment or close time: {opened}, {closed}")
    return [opened // 1000, *(float(value) for value in row[1:6])]


def validate_rows(rows, start, end):
    cursor = start
    gaps = []
    for row in rows:
        stamp, opened, high, low, closed, volume = row
        if stamp % 60 or not start <= stamp < end or stamp < cursor:
            raise ValueError(f"Invalid timestamp/order: {stamp}, expected >= {cursor}")
        if not all(math.isfinite(value) for value in row[1:]):
            raise ValueError(f"Nonfinite OHLCV at {stamp}")
        if min(opened, high, low, closed) <= 0 or volume < 0:
            raise ValueError(f"Nonpositive price or negative volume at {stamp}")
        if high < max(opened, closed, low) or low > min(opened, closed, high):
            raise ValueError(f"Invalid OHLC at {stamp}")
        if stamp > cursor:
            gaps.append({"start": cursor, "end_exclusive": stamp,
                         "missing_minutes": (stamp - cursor) // 60})
        cursor = stamp + 60
    if cursor < end:
        gaps.append({"start": cursor, "end_exclusive": end,
                     "missing_minutes": (end - cursor) // 60})
    return {"expected_rows": (end - start) // 60, "rows": len(rows),
            "missing_minutes": sum(gap["missing_minutes"] for gap in gaps), "gaps": gaps}


class Collector:
    def __init__(self, output):
        self.cache = output / "cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.sources = []

    def fetch(self, url, name, params=None, optional=False):
        path = self.cache / name
        metadata = path.with_name(path.name + ".source.json")
        if path.exists() and metadata.exists():
            data = path.read_bytes()
            record = json.loads(metadata.read_text())
            if record["url"] != url or record["params"] != params or record["sha256"] != sha(data):
                raise ValueError(f"Cache provenance/integrity mismatch: {path}")
            self.sources.append(record)
            return data
        for attempt in range(4):
            try:
                response = self.session.get(url, params=params, timeout=60)
                if response.status_code == 404 and optional:
                    self.sources.append({"url": url, "params": params, "status": 404})
                    return None
                response.raise_for_status()
                data = response.content
                record = {"url": url, "params": params, "sha256": sha(data),
                          "bytes": len(data), "cache_file": str(path),
                          "retrieved_at": iso(int(time.time()))}
                temporary = path.with_name(path.name + ".tmp")
                temporary.write_bytes(data)
                temporary.replace(path)
                metadata.write_text(json.dumps(record, indent=2) + "\n")
                self.sources.append(record)
                return data
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)

    def archive(self, symbol, period, kind, optional=False):
        filename = f"{symbol}-1m-{period}.zip"
        url = f"{ARCHIVES}/{kind}/klines/{symbol}/1m/{filename}"
        data = self.fetch(url, filename, optional=optional)
        if data is None:
            return None
        checksum = self.fetch(url + ".CHECKSUM", filename + ".CHECKSUM")
        expected, declared = checksum.decode().strip().split(maxsplit=1)
        if expected != sha(data) or declared.strip().lstrip("*") != filename:
            raise ValueError(f"Official archive checksum mismatch: {filename}")
        self.sources[-2]["official_checksum_verified"] = True
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.namelist()
            if len(members) != 1 or not members[0].endswith(".csv"):
                raise ValueError(f"Unexpected archive members: {members}")
            with archive.open(members[0]) as raw:
                reader = csv.reader(io.TextIOWrapper(raw))
                rows = []
                for row in reader:
                    if row[0] in ("open_time", "openTime"):
                        continue
                    rows.append(parse_kline(row))
        if not rows:
            raise ValueError(f"Empty archive: {filename}")
        validate_rows(rows, rows[0][0], rows[-1][0] + 60)
        print(f"{symbol}: verified {kind} {period}, {len(rows)} rows", flush=True)
        return rows

    def api(self, symbol, start, end):
        rows = []
        cursor = start
        while cursor < end:
            page_end = min(end, cursor + 1500 * 60)
            params = {"symbol": symbol, "interval": "1m", "startTime": cursor * 1000,
                      "endTime": page_end * 1000 - 1, "limit": 1500}
            data = self.fetch(API, f"{symbol}-api-{cursor}-{page_end}.json", params=params)
            page = json.loads(data)
            if not isinstance(page, list):
                raise ValueError(f"Unexpected API response: {page}")
            parsed = [parse_kline(row) for row in page if int(row[6]) < end * 1000
                      and int(row[6]) < int(time.time() * 1000)]
            validate_rows(parsed, cursor, page_end)
            rows.extend(parsed)
            cursor = page_end
        print(f"{symbol}: API fill {iso(start)} to {iso(end)}, {len(rows)} rows", flush=True)
        return rows

    def collect(self, symbol, start, end):
        rows = []
        cursor = datetime.fromtimestamp(start, timezone.utc).replace(hour=0, minute=0, second=0)
        while int(cursor.timestamp()) < end:
            month_end = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
            if cursor.day == 1 and int(month_end.timestamp()) <= end:
                segment = self.archive(symbol, cursor.strftime("%Y-%m"), "monthly")
                cursor = month_end
            else:
                day_end = cursor + timedelta(days=1)
                segment = self.archive(symbol, cursor.strftime("%Y-%m-%d"), "daily", optional=True)
                if segment is None:
                    segment = self.api(symbol, max(start, int(cursor.timestamp())),
                                       min(end, int(day_end.timestamp())))
                cursor = day_end
            rows.extend(row for row in segment if start <= row[0] < end)
        return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start", default="2026-04-01T00:00:00Z")
    parser.add_argument("--test-start", default="2026-04-13T15:00:00Z")
    parser.add_argument("--end", default="2026-10-13T15:00:00Z")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ZECUSDT"])
    args = parser.parse_args()
    start, test_start, end = utc(args.start), utc(args.test_start), utc(args.end)
    if not start <= test_start < end:
        parser.error("Require start <= test-start < end")
    if any(not symbol.isalnum() or not symbol.endswith("USDT") for symbol in args.symbols):
        parser.error("Symbols must be USDT contract identifiers")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {"exchange": "binance_um", "market_type": "USDT-margined perpetual futures",
                "interval": "1m", "timestamp_unit": "seconds", "timezone": "UTC",
                "source_documentation": "https://github.com/binance/binance-public-data",
                "start": iso(start), "test_start": iso(test_start), "end_exclusive": iso(end),
                "created_at": iso(int(time.time())), "symbols": {}}
    for symbol in args.symbols:
        collector = Collector(args.output)
        rows = collector.collect(symbol, start, end)
        coverage = validate_rows(rows, start, end)
        test_rows = [row for row in rows if row[0] >= test_start]
        test_coverage = validate_rows(test_rows, test_start, end)
        path = args.output / f"{symbol}-1m.csv"
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            writer.writerows(rows)
        manifest["symbols"][symbol] = {"csv": str(path.resolve()), "sha256": sha(path.read_bytes()),
                                         "first_timestamp": iso(rows[0][0]) if rows else None,
                                         "last_timestamp": iso(rows[-1][0]) if rows else None,
                                         **coverage, "test_window": test_coverage,
                                         "sources": collector.sources}
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"{symbol}: saved {len(rows)} rows; missing minutes {coverage['missing_minutes']}", flush=True)
    if any(item["missing_minutes"] for item in manifest["symbols"].values()):
        raise SystemExit("Minute gaps detected; manifest records actual data without fabrication")


if __name__ == "__main__":
    main()
