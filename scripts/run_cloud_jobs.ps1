# Runs the ML jobs (python -m pulse_ml.jobs: next-day BP predictions, ring night flags, weekly doctor reports) on one
# database connection. They write only ml_predictions, wearable_flags, weekly_reports and proposed patient_bands.
# Prints counts only (no health values).
# Connection: DATABASE_URL from the git-ignored .env; without it, a short-lived login from the linked Supabase CLI
# (the same one db push uses), passed as standard PG* variables. It is never printed or saved.
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
        $pg = @{}
        npx -y supabase@2.122.0 db dump --linked --dry-run 2>$null | ForEach-Object { if ($_ -match '^export (PG\w+)="?([^"]*)"?$') { $pg[$Matches[1]] = $Matches[2] } }
        if (-not $pg.PGPASSWORD) {
            Write-Host "No DATABASE_URL in .env and no linked Supabase CLI login (see docs/data/CLOUD_STEPS.md)." -ForegroundColor Red
            exit 1
        }
        foreach ($k in $pg.Keys) { Set-Item "Env:$k" $pg[$k] }   # standard libpq variables: no URL escaping
        $env:DATABASE_URL = "postgresql://"   # empty URI: libpq takes host, user, password from the PG* variables
        $env:PULSE_DB_ROLE = "postgres"   # the CLI login role acts as postgres, like the CLI itself (pulse_ml.predict.connect)
        Write-Host "Using a temporary login from the Supabase CLI ($($pg.PGHOST))." -ForegroundColor Cyan
    }
}
Set-Location ml
..\.venv\Scripts\python -m pulse_ml.jobs
$code = $LASTEXITCODE
Remove-Item Env:DATABASE_URL, Env:PULSE_DB_ROLE, Env:PGHOST, Env:PGPORT, Env:PGUSER, Env:PGPASSWORD, Env:PGDATABASE -ErrorAction SilentlyContinue
if ($code -ne 0) { Write-Host "STOPPED (exit $code)" -ForegroundColor Red; exit 1 }
Write-Host "Done." -ForegroundColor Green
