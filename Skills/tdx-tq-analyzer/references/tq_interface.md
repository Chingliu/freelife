# 通达信 TQ 接口参考

## What TQ is

通达信 V7.7x+ ships an official Python quant interface at `D:\tdx\PYPlugins\user\tqcenter.py` (observed v1.0.14, 2026-07-03). It wraps `TPythClient.dll` and talks to the running client in-process — this is the only officially supported way to get true intraday data from a local TDX terminal. Community libraries (`pytdx`/`mootdx`) broke after the 2026-07~09 server protocol change; do not use them.

## Environment facts (this machine)

- Client: `D:\tdx\TdxW.exe`, V7.73, 64-bit.
- Python with pandas: `C:\Users\ching\AppData\Local\Python\bin\python.exe` (3.14.2, pandas 3.0.5, numpy present). No pip install needed.
- Client log: `D:\tdx\T0001\tdxsys3.log` — login/data-download progress lives here (GBK-encoded).
- Server config: `D:\tdx\connect.cfg` — 43 quote hosts, port 7709.
- Plugin dir: `D:\tdx\PYPlugins\user\` — strategy scripts must live here.

## Connection recipe

```python
import sys
sys.path.insert(0, r"D:\tdx\PYPlugins\user")
from tqcenter import tq
tq.initialize(__file__)          # __file__ MUST be a path inside PYPlugins\user
snap = tq.get_market_snapshot(stock_code="510330.SH", field_list=[])
tq.close()
```

Failure signatures:
- `初始化错误：请确认是否打开通达信客户端` → script not in `PYPlugins\user`, OR client not running/logged in.
- `TQ数据接口初始化失败或已有同名策略运行` → same script name already registered; rename/remove the temp script and retry.
- Progress stuck at 71% then resets → first-login initialization data still downloading; wait.

## Key functions

| Function | Returns | Notes |
|---|---|---|
| `get_market_snapshot(stock_code, field_list=[])` | dict | Real-time quote: `Now`, `LastClose`, `Open`, `Max`, `Min`, `Avg`, `Volume` (lots), `Amount` (万元), `Inside`/`Outside` (active sell/buy volume), `Jjjz` (IOPV), `Zangsu`, `Buyp/Buyv/Sellp/Sellv` (5 levels) |
| `get_more_info(stock_code)` | dict | `HqDate`, `fHSL` (turnover %), `Zsz` (size 亿), `Wtb` (委比), `ZAFPre5/20/60`, `ZAFYear`, `CJJEPre1/3` |
| `get_stock_info(stock_code)` | dict | `Name`, `ActiveCapital` (shares), `J_mgjzc` (NAV), `underly_code` (index for ETF), `BelongRZRQ`, `BelongHSGT` |
| `get_market_data(stock_list=[...], period='1d', count=35, end_time='', dividend_type='none', field_list=[])` | dict of pandas-display strings | Fields: `Open/High/Low/Close/Volume/Amount/ForwardFactor`. `Volume` in shares, `Amount` in 万元. |

### Data truncation workaround
`get_market_data` returns a **string rendering of a DataFrame**, not a numeric structure. With `count > ~40`, pandas truncates the middle (`...`) and scientific-notation values can be clipped. Workaround: fetch in windows of `count=35` with `end_time` stepping back (e.g. `''`, `'20260915'`, `'20260715'`), then parse each line with a regex `r"\s*(\d{4}-\d{2}-\d{2})\s+([-\d.eE+]+)"` and merge by date. Scientific notation like `1.99e+08` must keep the `+`.

### Code format
Standard format is 6 digits + suffix: `600519.SH`, `000001.SZ`, `510330.SH`, `8xxxxx.BJ`. Use `get_stock_info` to confirm `Name` matches the intended security.

## Money-flow fields
There is no official "main capital flow" API in TQ. Available proxies:
- `Inside`/`Outside` from snapshot = active sell/buy volume (内外盘). Ratio and net = short-term signal.
- Chaikin Money Flow (CMF) computed from OHLCV = 20-day money-flow indicator (see `analysis_method.md`).
- `Zjl` field in `more_info` exists but is `0` for ETFs — do not rely on it.

## Maintenance notes
- Re-verify the interface after any 通达信 client update; `tqcenter.py` version is printed in its header.
- If `protocol` errors or all-zero data appear after a server-side change, fall back to community `tdxdata` (new-protocol implementation) or local `vipdoc` files for historical data.
