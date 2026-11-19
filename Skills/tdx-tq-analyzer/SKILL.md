---
name: tdx-tq-analyzer
description: Analyze any A-share stock or ETF through the official 通达信 (TDX) TQ Python interface — fetch real-time quote snapshots, daily K-lines, volume and active buy/sell (money-flow) data, then produce an ECharts HTML report with a volume/money-flow analysis and a defensible "buy basis" section (veto-first check, dimension table, trigger/stop/watchpoints triplet). Use when a user asks to pull live or historical quotes from 通达信, analyze 量能/资金流/买入依据 for a given stock or ETF, or reuse a local TDX client as a data source. Requires a Windows machine with 通达信 V7.7x+ installed at D:\tdx and a logged-in client.
agent_created: true
---

# 通达信 TQ 行情分析

## Overview

This skill turns a local 通达信 (TDX) terminal into a live/historical data source via its **official TQ Python interface (`tqcenter`)**, and produces a volume + money-flow analysis report for any specified stock or ETF. It encapsulates the hard-won setup details (script placement, login requirement, data truncation workaround) so the whole flow runs with one command.

## Critical constraints (read before acting)

1. **Client must be running AND logged in.** A launched-but-not-logged-in client cannot serve TQ. After login, wait until `D:\tdx\T0001\tdxsys3.log` shows `后台数据连接成功` / `后台数据处理完成`. First-ever login downloads initialization data and may take 10+ minutes (progress can roll back once).
2. **GUI auto-launch is often blocked by sandbox policy.** Do NOT try to launch `TdxW.exe` from inside the Python orchestrator. Use your own tools instead: PowerShell `Start-Process -FilePath 'D:\tdx\TdxW.exe' -WorkingDirectory 'D:\tdx'`, or a background shell `cd /d/tdx && ./TdxW.exe`. Keep it alive as a persistent background task — if the launching shell exits, the client may die with it.
3. **The fetch script must physically reside in `D:\tdx\PYPlugins\user`.** `tq.initialize(__file__)` launches `TPythClient` by the script's own path; running from anywhere else yields `初始化错误：请确认是否打开通达信客户端`. The orchestrator copies `tq_fetch.py` there temporarily and deletes it afterward.
4. **Python needs pandas + numpy.** A known-good interpreter on this machine: `C:\Users\ching\AppData\Local\Python\bin\python.exe` (3.14, pandas 3.0.5). The orchestrator probes candidates automatically.
5. **Data freshness**: when called during a live session, the latest daily bar is intraday (partial volume). The report tags this as 盘中快照; state this in the user-facing answer.

## Quick start

Run the whole pipeline for one code (code auto-normalized: `510330` → `510330.SH`, `000001` → `000001.SZ`, `8xxxxx` → `.BJ`):

```bash
"C:\Users\ching\AppData\Local\Python\bin\python.exe" \
  "D:\freelife\Skills\tdx-tq-analyzer\scripts\run_analysis.py" 510330 \
  --outdir "C:\path\to\output"
```

It prints `REPORT_HTML=<path>`. Open that HTML with the file viewer / browser. Outputs in `--outdir`:
- `report_<CODE>.html` — single integrated offline report with market analysis + six teaching chapters
- `metrics_<CODE>.json` / `chart_<CODE>.json` — analysis results
- `raw_<CODE>.json` — full raw TQ dump

If the client is already running, this is a single-shot command. If not, start it first (see constraint 2). `--skip-client-check` bypasses the running-process check (useful when `tasklist` is restricted).

## Workflow

1. **Confirm client state.** Check `tasklist` for `TdxW.exe`; if absent, start + log in per constraint 2. Never let the orchestrator launch the GUI.
2. **Run the orchestrator** with the target code and an output directory.
3. **Present the HTML report** to the user and summarize the key conclusion in text.
4. **Interpret with care** — see `references/analysis_method.md`. In particular: money-flow here is inferred from 内/外盘 and CMF, not real account flows; ETF volume spikes often reflect creation/redemption, not directional bets.

## Scripts

- `scripts/run_analysis.py` — orchestrator: code normalization → client check → temp script placement → fetch → analyze → report. Start here.
- `scripts/tq_fetch.py` — generic fetcher (runs from `PYPlugins\user`): snapshot, more_info, stock_info, and 3 windows × 35 daily bars.
- `scripts/analyze.py` — pure analysis: volume MAs, volume ratio, 20-day Chaikin Money Flow, up/down-day volume, top volume days; **plus the `buycase` block** (veto-first, dimension states, evidence cap, trigger/stop/watchpoints); writes metrics + chart JSON.
- `scripts/build_report.py` — renders the investment-analysis HTML with inline SVG charts and vanilla JavaScript; no CDN/network dependency. Includes a dedicated **买入依据核对** card.
- `scripts/course_content.py` — embeds six teaching chapters in the stock report, calculating real 510330 candle, volume, trend, multi-period and indicator examples.
- `scripts/learning_engine.py` — optional deterministic study-plan and mastery tracker.
- `scripts/learning_report.py` — legacy standalone progress page; not part of the normal report workflow.
- `learning/curriculum.json` — six-chapter curriculum outline.

## Learning system

See `LEARNING-SYSTEM.md`. The normal `run_analysis.py` workflow embeds all six chapters and real-data examples directly into `report_<CODE>.html`; do not generate a separate learning report for normal use.

## References

- `references/tq_interface.md` — TQ interface details: available functions, key data fields, the count>40 truncation workaround, probe recipe.
- `references/analysis_method.md` — volume & money-flow interpretation methodology and caveats.
- `references/buy_basis.md` — the 买入依据 framework: what was absorbed from the Cursor rules, the veto-first design, evidence-grade rules, and what is deliberately NOT claimed.
