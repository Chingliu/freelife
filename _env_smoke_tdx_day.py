"""Smoke-test reading Tongdaxin local .day bars from vipdoc."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VIPDOC = Path(r"D:\tdx\vipdoc")
RECORD_SIZE = 32


def read_day_file(path: Path) -> list[dict]:
    data = path.read_bytes()
    if len(data) % RECORD_SIZE != 0:
        raise ValueError(f"unexpected size {len(data)} for {path}")
    bars: list[dict] = []
    for i in range(0, len(data), RECORD_SIZE):
        # Tongdaxin .day: 32 bytes = 5*uint32 OHLC+date + float amount + uint32 vol + uint32 reserved
        date, open_, high, low, close, amount, vol, _reserved = struct.unpack(
            "<IIIIIfII", data[i : i + RECORD_SIZE]
        )
        bars.append(
            {
                "date": date,
                "open": open_ / 100.0,
                "high": high / 100.0,
                "low": low / 100.0,
                "close": close / 100.0,
                "amount": amount,
                "volume": vol,
            }
        )
    return bars


def main() -> int:
    print(f"Python: {sys.version}")
    print(f"vipdoc: {VIPDOC} exists={VIPDOC.exists()}")
    if not VIPDOC.exists():
        return 1

    counts = {}
    for market in ("sh", "sz", "bj"):
        lday = VIPDOC / market / "lday"
        n = len(list(lday.glob("*.day"))) if lday.exists() else 0
        counts[market] = n
        print(f"  {market}/lday: {n} files")

    samples = [
        VIPDOC / "sh" / "lday" / "sh600000.day",
        VIPDOC / "sz" / "lday" / "sz000001.day",
        VIPDOC / "sh" / "lday" / "sh000001.day",
    ]
    ok = 0
    for sample in samples:
        if not sample.exists():
            print(f"MISSING {sample}")
            continue
        bars = read_day_file(sample)
        first, last = bars[0], bars[-1]
        print(
            f"OK {sample.name}: bars={len(bars)} "
            f"first={first['date']} close={first['close']:.2f} "
            f"last={last['date']} close={last['close']:.2f}"
        )
        ok += 1

    total = sum(counts.values())
    print(f"TOTAL_DAY_FILES={total} SAMPLES_OK={ok}")
    return 0 if ok >= 2 and total > 1000 else 2


if __name__ == "__main__":
    raise SystemExit(main())
