# -*- coding: utf-8 -*-
"""
TQ generic data fetcher for one security.

IMPORTANT: This script must be executed from inside the 通达信
`PYPlugins\\user` directory, because tqcenter launches TPythClient
by the script's own path. The orchestrator (run_analysis.py) copies
this file there automatically.

Usage (from PYPlugins\\user):
    python tq_fetch.py <CODE> <OUTPUT_JSON>

Example:
    python tq_fetch.py 510330.SH C:\\tmp\\raw.json
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tqcenter import tq  # noqa: E402

NUM_RE = re.compile(r"\s*(\d{4}-\d{2}-\d{2})\s+([-\d.eE+]+)")


def parse_block(txt):
    """Parse a get_market_data field into {date: float}.

    TQ has been observed returning BOTH a pandas DataFrame and its string
    rendering, depending on client state / call path. Handle both.
    """
    rows = {}
    # DataFrame: values are already numeric (most reliable path)
    if hasattr(txt, "index") and hasattr(txt, "values"):
        try:
            for d, v in zip(txt.index, txt.values):
                val = float(v[0]) if hasattr(v, "__len__") and not isinstance(v, str) else float(v)
                rows[str(d)[:10]] = val
        except (ValueError, TypeError, IndexError):
            pass
        return rows
    if not isinstance(txt, str):
        return rows
    for line in txt.strip().splitlines():
        m = NUM_RE.match(line)
        if not m:
            continue
        try:
            rows[m.group(1)] = float(m.group(2))
        except ValueError:
            # pandas may render scientific notation oddly; try recover exponent
            v = m.group(2)
            if v.endswith("e"):
                try:
                    rows[m.group(1)] = float(v + "+08")
                except ValueError:
                    pass
    return rows


def fetch(code, out_path):
    tq.initialize(__file__)
    raw = {"code": code, "snapshot": {}, "more_info": {}, "stock_info": {}, "windows": {}}
    raw["snapshot"] = tq.get_market_snapshot(stock_code=code, field_list=[])
    raw["more_info"] = tq.get_more_info(stock_code=code, field_list=[])
    raw["stock_info"] = tq.get_stock_info(stock_code=code, field_list=[])

    # 3 windows x 35 bars ~= 105 trading days; avoids pandas str truncation at count>40
    # NOTE: pass field_list=[] (all fields). An explicit field_list can return
    # empty windows on some client states; all-fields is the robust path.
    for end in ["", "20260915", "20260715"]:
        res = tq.get_market_data(
            field_list=[], stock_list=[code], period="1d", count=35,
            end_time=end, dividend_type="none",
        )
        window = {}
        for field in ["Open", "High", "Low", "Close", "Volume", "Amount"]:
            window[field] = parse_block(res.get(field, ""))
        raw["windows"][end or "latest"] = window
        if not window["Close"] and end == "":
            # post-close cache can be stale: refresh then retry once
            try:
                tq.refresh_cache()
            except Exception:
                pass
            res = tq.get_market_data(
                field_list=[], stock_list=[code], period="1d", count=35,
                end_time=end, dividend_type="none",
            )
            for field in ["Open", "High", "Low", "Close", "Volume", "Amount"]:
                window[field] = parse_block(res.get(field, ""))

    tq.close()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, default=str)
    return raw


def main():
    if len(sys.argv) < 3:
        print("Usage: python tq_fetch.py <CODE> <OUTPUT_JSON>")
        sys.exit(2)
    code, out = sys.argv[1], sys.argv[2]
    try:
        raw = fetch(code, out)
    except Exception as exc:
        print(f"FETCH_FAILED: {type(exc).__name__}: {exc}")
        sys.exit(1)
    snap = raw.get("snapshot", {})
    print("FETCH_OK")
    print("CODE", code)
    print("NOW", snap.get("Now"))
    print("OUT", out)


if __name__ == "__main__":
    main()
