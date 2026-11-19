# Daily ETF playbook — thin wrapper. Prefer the Python entry directly:
#   D:\freelife\.venv\Scripts\python.exe D:\freelife\AIStockAssistant\scripts\run_daily_etf_playbook.py
#
# Do NOT Tee-Object Python output into run.log: with $ErrorActionPreference=Stop,
# the first stderr line aborts the job (seen 2026-07-29 17:00).
#
# Exit codes: 0=ok, 1=report failed, 2=report ok but sync/email partial failure

param(
    [switch]$SkipSync,
    [switch]$NotifyTest,
    [switch]$NoNotify,
    [string]$Codes = "",
    [string]$OutDir = "reports/daily"
)

$Root = Split-Path -Parent $PSScriptRoot
$Python = "D:\freelife\.venv\Scripts\python.exe"
$Runner = Join-Path $PSScriptRoot "run_daily_etf_playbook.py"

if (-not (Test-Path $Python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $Python = $cmd.Source } else {
        Write-Error "Python not found. Expected D:\freelife\.venv\Scripts\python.exe"
        exit 1
    }
}
if (-not (Test-Path $Runner)) {
    Write-Error "Missing runner: $Runner"
    exit 1
}

$argList = @($Runner, "--out-dir", $OutDir)
if ($Codes) { $argList += @("--codes", $Codes) }
if ($SkipSync) { $argList += "--skip-sync" }
if ($NoNotify) { $argList += "--no-notify" }
if ($NotifyTest) { $argList += "--notify-test" }

# No Tee-Object, no Stop-on-stderr — let Python own logging + rotation.
& $Python @argList
exit $LASTEXITCODE
