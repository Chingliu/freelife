# -*- coding: utf-8 -*-
"""
Orchestrator: analyze any stock/ETF via 通达信 official TQ interface.

End-to-end pipeline:
  1. Normalize the security code (add .SH/.SZ/.BJ suffix if missing).
  2. Verify TdxW.exe is running; auto-start + wait for login if needed.
  3. Locate a Python interpreter with pandas+numpy.
  4. Copy tq_fetch.py into D:\\tdx\\PYPlugins\\user (TQ requires scripts there),
     run it to dump raw data to JSON, then remove the temp copy.
  5. Run analyze.py -> metrics.json + chart.json
  6. Run build_report.py -> HTML report
  7. Print all output paths.

Usage:
    python run_analysis.py <CODE> [--outdir DIR] [--skip-client-check]

Examples:
    python run_analysis.py 510330
    python run_analysis.py 600519.SH --outdir C:\\reports
    python run_analysis.py 000001
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TDX_DIR = Path(r"D:\tdx")
TDX_EXE = TDX_DIR / "TdxW.exe"
PY_USER_DIR = TDX_DIR / "PYPlugins" / "user"
SCRIPTS_DIR = Path(__file__).resolve().parent


def normalize_code(raw):
    code = raw.strip().upper()
    if re.match(r"^\d{6}\.(SH|SZ|BJ)$", code):
        return code
    digits = re.sub(r"\D", "", code)
    if not re.match(r"^\d{6}$", digits):
        raise ValueError(f"无法识别证券代码: {raw}")
    if digits[0] in "569":
        suffix = "SH"
    elif digits[0] in "03":
        suffix = "SZ"
    elif digits[0] in "48":
        suffix = "BJ"
    else:
        suffix = "SH"
    return f"{digits}.{suffix}"


def find_python():
    candidates = [
        r"C:\Users\ching\AppData\Local\Python\bin\python.exe",
        sys.executable,
        "python",
    ]
    for p in candidates:
        try:
            r = subprocess.run(
                [p, "-c", "import pandas, numpy"],
                capture_output=True, timeout=30,
            )
            if r.returncode == 0:
                return p
        except Exception:
            continue
    raise RuntimeError("未找到带 pandas/numpy 的 Python 解释器，请先安装: pip install pandas numpy")


def _decode(b):
    """Decode Windows console output (usually GBK on zh-CN systems)."""
    for enc in ("utf-8", "gbk", "cp936"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


def tdx_running():
    try:
        r = subprocess.run(["tasklist"], capture_output=True, timeout=15)
        out = _decode(r.stdout)
        return "TdxW.exe" in out
    except Exception:
        return False


def ensure_client():
    """Verify the client is up. Do NOT auto-launch: GUI launches are often
    blocked by sandbox policy. The calling agent should start it with its own
    tools (PowerShell Start-Process / background shell) if needed."""
    if tdx_running():
        print("[OK] 通达信客户端已在运行")
        return
    raise RuntimeError(
        "通达信客户端未运行。请先用 PowerShell 启动并登录：\n"
        "  Start-Process -FilePath 'D:\\tdx\\TdxW.exe' -WorkingDirectory 'D:\\tdx'\n"
        "首次登录需下载初始化数据，wait 到日志出现「后台数据连接成功」后重试本脚本。"
    )


def run(cmd, **kw):
    print("[RUN]", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code", help="证券代码，如 510330 / 600519.SH / 000001")
    ap.add_argument("--outdir", default=None, help="输出目录，默认当前目录")
    ap.add_argument("--skip-client-check", action="store_true")
    args = ap.parse_args()

    code = normalize_code(args.code)
    print(f"[OK] 规范化代码: {code}")

    outdir = Path(args.outdir).resolve() if args.outdir else Path.cwd().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    if not args.skip_client_check:
        if not TDX_EXE.exists():
            raise RuntimeError(f"未找到通达信: {TDX_EXE}")
        ensure_client()

    py = find_python()
    print(f"[OK] Python: {py}")

    raw_path = outdir / f"raw_{code.replace('.', '_')}.json"
    metrics_path = outdir / f"metrics_{code.replace('.', '_')}.json"
    chart_path = outdir / f"chart_{code.replace('.', '_')}.json"
    html_path = outdir / f"report_{code.replace('.', '_')}.html"

    # TQ requires the strategy script to live in PYPlugins\\user
    temp_name = f"_fetch_{code.split('.')[0]}.py"
    temp_path = PY_USER_DIR / temp_name
    src = SCRIPTS_DIR / "tq_fetch.py"
    if not PY_USER_DIR.exists():
        raise RuntimeError(f"PYPlugins/user 目录不存在: {PY_USER_DIR}")
    shutil.copy2(src, temp_path)
    print(f"[OK] 已放置采集脚本: {temp_path}")
    try:
        run([py, str(temp_path), code, str(raw_path)],
            cwd=str(PY_USER_DIR), capture_output=False)
    except subprocess.CalledProcessError as e:
        print("[ERR] 采集失败。常见原因：客户端未登录 / 同名策略已在运行。")
        raise
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass

    run([py, str(SCRIPTS_DIR / "analyze.py"), str(raw_path),
         str(metrics_path), str(chart_path)], capture_output=False)
    run([py, str(SCRIPTS_DIR / "build_report.py"), str(metrics_path),
         str(chart_path), str(html_path)], capture_output=False)

    print("\n=== 产出文件 ===")
    for p in [html_path, metrics_path, chart_path, raw_path]:
        print(p)
    print("\nREPORT_HTML=" + str(html_path))


if __name__ == "__main__":
    main()
