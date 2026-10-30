# Runs the ML jobs against the database in DATABASE_URL (from the git-ignored .env): next-day BP predictions,
# ring night flags, weekly doctor reports. They write only ml_predictions, wearable_flags, weekly_reports and
# proposed patient_bands. Prints counts only (no health values).
# Run from the repo root:   powershell -ExecutionPolicy Bypass -File scripts\run_cloud_jobs.ps1
# Test on the local stack:  powershell -ExecutionPolicy Bypass -File scripts\run_cloud_jobs.ps1 -Local
param([switch]$Local)
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($Local) {
    $env:DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:55322/postgres"
} else {
    $line = Get-Content .env -ErrorAction SilentlyContinue | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
    if (-not $line) {
        Write-Host "No DATABASE_URL in .env. Add the Session pooler connection string first (see docs/data/CLOUD_STEPS.md)." -ForegroundColor Red
        exit 1
    }
    $env:DATABASE_URL = $line.Substring(13).Trim().Trim('"')
}
Set-Location ml
foreach ($job in @(@("pulse_ml.predict", "--all"), @("pulse_ml.monitor", "--nights"), @("pulse_ml.weekly"))) {
    Write-Host ("running " + ($job -join " ")) -ForegroundColor Cyan
    ..\.venv\Scripts\python -m @job
    if ($LASTEXITCODE -ne 0) { Write-Host "STOPPED at $($job[0])" -ForegroundColor Red; exit 1 }
}
Remove-Item Env:DATABASE_URL
Write-Host "Done." -ForegroundColor Green
