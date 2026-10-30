# Applies pending migrations (M8 chronic_conditions) and refreshes the SIMULATED ring demo in the cloud project.
# Run from the repo root (Desktop\pulse):   powershell -ExecutionPolicy Bypass -File scripts\cloud_update.ps1
# Test on the local stack instead:          powershell -ExecutionPolicy Bypass -File scripts\cloud_update.ps1 -Local
# It deletes ONLY simulated samples of the demo rings; BP readings, accounts and everything else stay.
param([switch]$Local)
Set-Location (Split-Path $PSScriptRoot -Parent)
$cli = "supabase@2.122.0"
$target = if ($Local) { "--local" } else { "--linked" }
function Check($step) { if ($LASTEXITCODE -ne 0) { Write-Host "STOPPED at: $step" -ForegroundColor Red; exit 1 } }

Write-Host "1/4  Pending migrations ($target):" -ForegroundColor Cyan
if ($Local) { npx -y $cli migration up --local; Check "migrations" }
else {
    npx -y $cli db push --linked --dry-run; Check "dry run"
    Write-Host "2/4  Applying migrations..." -ForegroundColor Cyan
    "y" | npx -y $cli db push --linked; Check "db push"
}

Write-Host "3/4  Refreshing the simulated ring demo (5 parts)..." -ForegroundColor Cyan
Remove-Item data\cloud_ring_demo_part*.sql -ErrorAction SilentlyContinue
.venv\Scripts\python -m pulse_data.simulate ring-demo-sql; Check "generate ring demo"
Get-ChildItem data\cloud_ring_demo_part*.sql | Sort-Object { [int]($_.BaseName -replace '\D', '') } | ForEach-Object {
    Write-Host "     $($_.Name)"
    npx -y $cli db query $target -f $_.FullName | Out-Null; Check $_.Name
}

Write-Host "4/4  Check (expected: readings 730, ring patients 12, ring samples 20832, copd 1):" -ForegroundColor Cyan
npx -y $cli db query $target ("select (select count(*) from public.measurements) readings, " +
    "(select count(distinct patient_id) from public.wearable_samples) ring_patients, " +
    "(select count(*) from public.wearable_samples where source = 'simulated') ring_samples, " +
    "(select count(*) from public.patient_profiles where 'copd' = any(condition_codes)) copd")
Write-Host "Done." -ForegroundColor Green
