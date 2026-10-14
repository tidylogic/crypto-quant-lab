#!/usr/bin/env python3
"""Download public MEXC perpetual candles, preserving raw provenance and gaps.

The documented open/high/low/close arrays are used consistently. Min3 is not
offered by MEXC; callers must aggregate complete sets of native Min1 candles.
"""
import argparse
import concurrent.futures
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import threading
import time

import requests

BASE_URL = "https://api.mexc.com/api/v1/contract/kline/"
DOC_URL = "https://www.mexc.com/api-docs/futures/market-endpoints/get-candlestick-data"
FIELDS = ("open", "high", "low", "close", "vol")


def iso(timestamp):
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat()


def decode(payload, start, end, step):
    """Validate arrays and select the half-open request range without filling gaps."""
    if not payload.get("success") or payload.get("code") != 0:
        raise ValueError(f"MEXC rejected request: {payload}")
    data = payload["data"]
    times = data["time"]
    if any(len(data[field]) != len(times) for field in FIELDS):
        raise ValueError("MEXC returned inconsistent array lengths")
    differences = {}
    rows = []
    previous = None
    for i, timestamp in enumerate(times):
        timestamp = int(timestamp)
        if timestamp % step or (previous is not None and timestamp <= previous):
            raise ValueError(f"Unaligned/non-increasing candle timestamp: {timestamp}")
        previous = timestamp
        values = tuple(float(data[field][i]) for field in FIELDS)
        if any(not math.isfinite(v) or v <= 0 for v in values[:4]):
            raise ValueError(f"Invalid candle price at {timestamp}")
        if not math.isfinite(values[4]) or values[4] < 0:
            raise ValueError(f"Invalid candle volume at {timestamp}")
        if not start <= timestamp < end:
            continue
        rows.append((timestamp, *values))
        for field in FIELDS[:4]:
            real = "real" + field.capitalize()
            if real in data:
                if len(data[real]) != len(times):
                    raise ValueError(f"Inconsistent {real} array length")
                difference = abs(float(data[field][i]) - float(data[real][i]))
                item = differences.setdefault(field, {"different_count": 0, "max_absolute_difference": 0.0})
                item["different_count"] += int(difference != 0)
                item["max_absolute_difference"] = max(item["max_absolute_difference"], difference)
    return rows, differences


def audit_rows(rows, start, end, step):
    expected = (end - start) // step
    cursor = start
    gaps = []
    for row in rows:
        timestamp = row[0]
        if timestamp < cursor or timestamp % step or timestamp >= end:
            raise ValueError("Merged dataset has duplicated, disordered, or out-of-range candles")
        if timestamp > cursor:
            gaps.append({"start": cursor, "end_exclusive": timestamp,
                         "missing_candles": (timestamp - cursor) // step})
        cursor = timestamp + step
    if cursor < end:
        gaps.append({"start": cursor, "end_exclusive": end,
                     "missing_candles": (end - cursor) // step})
    return {"expected_candles": expected, "candle_count": len(rows),
            "first_timestamp": rows[0][0] if rows else None,
            "last_timestamp": rows[-1][0] if rows else None,
            "first_utc": iso(rows[0][0]) if rows else None,
            "last_utc": iso(rows[-1][0]) if rows else None,
            "missing_candles": sum(g["missing_candles"] for g in gaps), "gaps": gaps,
            "ohlc_bounds_mismatch_count": sum(not (r[3] <= r[1] <= r[2] and r[3] <= r[4] <= r[2]) for r in rows)}


class Downloader:
    def __init__(self, directory):
        self.directory = directory
        self.raw = directory / "raw"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.last_request = 0.0

    def fetch(self, symbol, interval, start, end, step):
        params = {"interval": interval, "start": start, "end": end - 1}
        url = requests.Request("GET", BASE_URL + symbol, params=params).prepare().url
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.raw / (key + ".json")
        meta_path = self.raw / (key + ".meta.json")
        if path.exists() and meta_path.exists():
            raw = path.read_bytes()
            meta = json.loads(meta_path.read_text())
            if hashlib.sha256(raw).hexdigest() != meta["sha256"]:
                raise ValueError(f"Cached response checksum mismatch: {path}")
        else:
            for attempt in range(5):
                with self.lock:
                    delay = 0.22 - (time.monotonic() - self.last_request)
                    if delay > 0:
                        time.sleep(delay)
                    self.last_request = time.monotonic()
                try:
                    response = requests.get(url, timeout=45)
                    response.raise_for_status()
                    raw = response.content
                    payload = response.json()
                    if not payload.get("success") or payload.get("code") != 0:
                        raise ValueError(f"MEXC error {payload}")
                    break
                except (requests.RequestException, ValueError):
                    if attempt == 4:
                        raise
                    time.sleep(1 + attempt * 2)
            meta = {"url": url, "params": params, "symbol": symbol,
                    "fetched_at_utc": iso(int(time.time())), "http_status": response.status_code,
                    "sha256": hashlib.sha256(raw).hexdigest(), "raw_path": str(path.resolve())}
            path.write_bytes(raw)
            meta_path.write_text(json.dumps(meta, indent=2))
        payload = json.loads(raw)
        rows, differences = decode(payload, start, end, step)
        meta = dict(meta, requested_start=start, requested_end_exclusive=end,
                    returned_count=len(payload["data"]["time"]), accepted_count=len(rows),
                    accepted_first_timestamp=rows[0][0] if rows else None,
                    accepted_last_timestamp=rows[-1][0] if rows else None)
        return rows, differences, meta

    def dataset(self, symbol, interval, start, end, step):
        ranges = [(s, min(s + 2000 * step, end)) for s in range(start, end, 2000 * step)]
        merged = {}
        differences = {}
        requests_log = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(self.fetch, symbol, interval, a, b, step) for a, b in ranges]
            for future in concurrent.futures.as_completed(futures):
                rows, diff, meta = future.result()
                requests_log.append(meta)
                for row in rows:
                    if row[0] in merged and merged[row[0]] != row:
                        raise ValueError(f"Conflicting repeated candle at {row[0]}")
                    merged[row[0]] = row
                for field, item in diff.items():
                    aggregate = differences.setdefault(field, {"different_count": 0, "max_absolute_difference": 0.0})
                    aggregate["different_count"] += item["different_count"]
                    aggregate["max_absolute_difference"] = max(aggregate["max_absolute_difference"], item["max_absolute_difference"])
        rows = sorted(merged.values())
        path = self.directory / f"{symbol}-{interval}.csv"
        with path.open("w", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(("timestamp", "open", "high", "low", "close", "volume"))
            writer.writerows(rows)
        return dict(audit_rows(rows, start, end, step), symbol=symbol, interval=interval,
                    requested_start=start, requested_end_exclusive=end,
                    csv_path=str(path.resolve()), csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    documented_vs_real_fields=differences,
                    requests=sorted(requests_log, key=lambda r: r["requested_start"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-04-13T15:00:00+00:00")
    parser.add_argument("--end", default="2026-10-13T15:00:00+00:00")
    parser.add_argument("--output", type=Path, default=Path("user_data/data/ppp-mexc"))
    parser.add_argument("--symbols", nargs="+", default=["BTC_USDT", "ZEC_USDT"])
    parser.add_argument("--intervals", nargs="+", default=["Min5", "Min15", "Min1"], choices=["Min1", "Min5", "Min15"])
    args = parser.parse_args()
    start = int(dt.datetime.fromisoformat(args.start).timestamp())
    end = int(dt.datetime.fromisoformat(args.end).timestamp())
    if end <= start or end > int(time.time()) // 900 * 900 or start % 900 or end % 900:
        parser.error("Use closed, UTC quarter-hour aligned start/end bounds")
    downloader = Downloader(args.output)
    manifest_path = args.output / "manifest.json"
    manifest = {"exchange": "MEXC", "market": "USDT perpetual futures", "source_base_url": BASE_URL,
                "documentation_url": DOC_URL, "price_fields": "documented open/high/low/close",
                "domain_update_source_url": "https://www.mexc.com/announcements/api-updates",
                "volume_units": "MEXC reported contract volume (vol)",
                "test_start": start, "test_end_exclusive": end, "test_start_utc": iso(start),
                "test_end_exclusive_utc": iso(end), "created_at_utc": iso(int(time.time())),
                "notes": ["Missing bars are preserved as gaps; no synthetic candles.",
                          "Min3 is unsupported; aggregate complete native Min1 bars separately.",
                          "Native Min1 is probed over 33 days before the fixed evaluation end."],
                "datasets": [], "api_probes": []}
    for interval in args.intervals:
        step = {"Min1": 60, "Min5": 300, "Min15": 900}[interval]
        data_start = end - 33 * 86400 if interval == "Min1" else start - 1000 * step
        for symbol in args.symbols:
            print(f"Fetching {symbol} {interval} {iso(data_start)} to {iso(end)}", flush=True)
            result = downloader.dataset(symbol, interval, data_start, end, step)
            manifest["datasets"].append(result)
            manifest["updated_at_utc"] = iso(int(time.time()))
            manifest_path.write_text(json.dumps(manifest, indent=2))
            print(json.dumps({k: result[k] for k in ["symbol", "interval", "candle_count", "first_utc", "last_utc", "missing_candles", "gaps", "ohlc_bounds_mismatch_count"]}), flush=True)
    one_minute = [d for d in manifest["datasets"] if d["interval"] == "Min1" and d["first_timestamp"] is not None]
    if len(one_minute) == len(args.symbols):
        first = max(d["first_timestamp"] for d in one_minute)
        manifest["minute_common_available_first"] = first
        manifest["minute_common_evaluation_start_with_600_minute_warmup"] = (first + 600 * 60 + 899) // 900 * 900
        manifest["minute_common_evaluation_start_utc"] = iso(manifest["minute_common_evaluation_start_with_600_minute_warmup"])
        for dataset in one_minute:
            boundary = dataset["first_timestamp"]
            for probe_start in (boundary - 60, boundary):
                _, _, meta = downloader.fetch(dataset["symbol"], "Min1", probe_start, probe_start + 60, 60)
                meta["purpose"] = "native_one_minute_availability_boundary"
                manifest["api_probes"].append(meta)
                print(f"Boundary probe {dataset['symbol']} {iso(probe_start)}: {meta['accepted_count']} candles", flush=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest: {manifest_path.resolve()}", flush=True)


if __name__ == "__main__":
    main()
