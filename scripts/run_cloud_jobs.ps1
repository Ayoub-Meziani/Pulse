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
    if ($line) {
        $env:DATABASE_URL = $line.Substring(13).Trim().Trim('"')
    } else {
        # No password in .env: short-lived login from the linked Supabase CLI (the same one db push uses). Never printed.
        $pg = @{}
        npx -y supabase@2.122.0 db dump --linked --dry-run 2>$null | ForEach-Object { if ($_ -match '^export (PG\w+)="?([^"]*)"?$') { $pg[$Matches[1]] = $Matches[2] } }
        if (-not $pg.PGPASSWORD) {
            Write-Host "No DATABASE_URL in .env and no linked Supabase CLI login (see docs/data/CLOUD_STEPS.md)." -ForegroundColor Red
            exit 1
        }
        $env:DATABASE_URL = "postgresql://$($pg.PGUSER):$([uri]::EscapeDataString($pg.PGPASSWORD))@$($pg.PGHOST):$($pg.PGPORT)/$($pg.PGDATABASE)"
        $env:PULSE_DB_ROLE = "postgres"   # the CLI login role acts as postgres, like the CLI itself (pulse_ml.predict.connect)
        Write-Host "Using a temporary login from the Supabase CLI ($($pg.PGHOST))." -ForegroundColor Cyan
    }
}
Set-Location ml
foreach ($job in @(@("pulse_ml.predict", "--all"), @("pulse_ml.monitor", "--nights"), @("pulse_ml.weekly"))) {
    Write-Host ("running " + ($job -join " ")) -ForegroundColor Cyan
    ..\.venv\Scripts\python -m @job
    if ($LASTEXITCODE -ne 0) { Write-Host "STOPPED at $($job[0])" -ForegroundColor Red; exit 1 }
}
Remove-Item Env:DATABASE_URL, Env:PULSE_DB_ROLE -ErrorAction SilentlyContinue
Write-Host "Done." -ForegroundColor Green
