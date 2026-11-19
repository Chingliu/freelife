"""Local smoke check for Tongdaxin price scaling and bar sanity.

Usage:
  python -m app.tools.smoke_tdx
  python -m app.tools.smoke_tdx --vipdoc D:\\tdx\\vipdoc
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config.settings import Settings
from app.data.tdx_day_reader import price_divisor, read_day_file

# Keep in sync with tests/test_smoke_tdx_prices.py LIVE_PRICE_BANDS
ANCHORS: dict[str, tuple[float, float]] = {
    "sh600000": (2.0, 40.0),
    "sz000001": (2.0, 40.0),
    "sh000001": (1500.0, 8000.0),
    "sz399001": (4000.0, 30000.0),
    "sh510050": (1.0, 10.0),
    "sh510300": (1.5, 15.0),
    "sz159915": (0.8, 10.0),
    "sh511880": (90.0, 110.0),
    "sh511010": (80.0, 200.0),
}


def _check_vipdoc(vipdoc: Path) -> list[str]:
    errors: list[str] = []
    if not vipdoc.is_dir():
        return [f"vipdoc missing: {vipdoc}"]

    checked = 0
    for code, (lo, hi) in ANCHORS.items():
        path = vipdoc / code[:2] / "lday" / f"{code}.day"
        if not path.is_file():
            print(f"  SKIP {code}: file not found")
            continue
        bars = read_day_file(path)
        if not bars:
            errors.append(f"{code}: empty")
            continue
        last = bars[-1]
        checked += 1
        ok = lo <= last.close <= hi
        status = "OK" if ok else "FAIL"
        print(
            f"  {status} {code}: close={last.close:.4f} "
            f"band=[{lo},{hi}] date={last.trade_date} div={price_divisor(code):.0f}"
        )
        if not ok:
            errors.append(
                f"{code}: close={last.close} outside [{lo},{hi}] "
                f"(possible wrong price_divisor={price_divisor(code)})"
            )
        if last.high < max(last.open, last.close) - 1e-9:
            errors.append(f"{code}: OHLC invariant high broken")
        if last.low > min(last.open, last.close) + 1e-9:
            errors.append(f"{code}: OHLC invariant low broken")

    if checked < 3:
        errors.append(f"only {checked} anchors found; need >= 3")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TDX price-scale smoke check")
    parser.add_argument("--vipdoc", type=str, default="", help="override vipdoc path")
    args = parser.parse_args(argv)

    if args.vipdoc:
        vipdoc = Path(args.vipdoc)
    else:
        vipdoc = Path(Settings.load().data.tdx.vipdoc)

    print(f"smoke_tdx vipdoc={vipdoc}")
    errors = _check_vipdoc(vipdoc)
    if errors:
        print("FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
