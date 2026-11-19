# Daily ETF playbook (Windows)

## Manual smoke

```powershell
cd D:\freelife\AIStockAssistant
D:\freelife\.venv\Scripts\python.exe -m app.main research-playbook --notify-test
```

Full report + email (preferred entry — **Python**, not PowerShell Tee-Object):

```powershell
D:\freelife\.venv\Scripts\python.exe D:\freelife\AIStockAssistant\scripts\run_daily_etf_playbook.py
# skip EOD sync when data already fresh:
D:\freelife\.venv\Scripts\python.exe D:\freelife\AIStockAssistant\scripts\run_daily_etf_playbook.py --skip-sync
```

Outputs under `reports/daily/`:

- `YYYY-MM-DD.md` / `.html` / `.json` — playbook
- `charts/YYYY-MM-DD/{code}_price.png` / `{code}_rsi.png` — 看图说话静态图
- `YYYY-MM-DD.status.json` — step diagnostics
- `run.log` — **structured** step lines only (UTF-8, rotated at ~2 MiB, keeps 3 backups)
- `verbose.log` — INFO/WARNING detail from sync/backtest (RotatingFileHandler, 5 MiB × 3)

邮件正文为 **看图说话 HTML**（价格地势 + RSI 图 CID 内嵌、白话台阶、分批 L1→R2、决策/信号表）；
附件同时带 `.html`、`.md` 与图表 PNG（CID 被客户端剥离时仍可打开附件）。
本地预览：打开 `YYYY-MM-DD.html`（相对路径引用 `charts/...`）。

`--notify-test` 仅测 SMTP 连通，不生成图表日报。完整干跑（不出信；CLI 默认不同步 EOD）：

```powershell
D:\freelife\.venv\Scripts\python.exe -m app.main research-playbook --no-notify
```

Exit codes: `0` all ok, `1` report failed, `2` report ok but sync/email failed.

## Why not Tee-Object into run.log

`$ErrorActionPreference=Stop` + `python 2>&1 | Tee-Object -Append run.log` aborts on the **first stderr line** (e.g. Traceback prefix or library noise), kills the child mid-sync, and Tee-Object rewrites chunks as UTF-16 (~2× size). That failed the 2026-07-29 17:00 job after ~5 minutes of sync with no report/email.

## Schedule 17:00 weekdays

```powershell
schtasks /Create /F /TN "AIStockAssistant-ETF-Playbook" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 17:00 /TR "D:\freelife\.venv\Scripts\python.exe D:\freelife\AIStockAssistant\scripts\run_daily_etf_playbook.py" /RL LIMITED
```

Optional: in Task Scheduler, disable “Start only if on AC power” / “Stop if switching to battery” for laptops.

Configure SMTP in repo-root `env.local.yaml` under `notify.email` (QQ auth code, not login password).
