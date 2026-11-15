# Prepare the demo data in one go, from the repo root:
#     powershell -ExecutionPolicy Bypass -File scripts\prepare_demo.ps1
# Optional: also process all 19,742 articles afterwards (long; the scale number for the pitch):
#     powershell -ExecutionPolicy Bypass -File scripts\prepare_demo.ps1 -All
#
# Each step's time is appended to data\timings.txt (numbers for the README and the deck).
# A failing step is reported and the script carries on with the next one.
param([switch]$All)

$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force -Path data | Out-Null
$log = "data\timings.txt"
"=== prepare_demo $(Get-Date -Format 'yyyy-MM-dd HH:mm') ===" | Add-Content $log

function Step($name, [string[]]$cmd) {
    Write-Host "`n>>> $name" -ForegroundColor Yellow
    Write-Host "    python $($cmd -join ' ')"
    $t = Measure-Command { & python @cmd | Out-Host }
    $ok = if ($LASTEXITCODE -eq 0) { "ok" } else { "FAILED (exit $LASTEXITCODE)" }
    $line = "{0,-45} {1,8:N1} s  {2}" -f $name, $t.TotalSeconds, $ok
    Write-Host "    $line" -ForegroundColor Cyan
    $line | Add-Content $log
}

$hasGemma = (Test-Path .env) -and (Select-String -Path .env -Pattern '^\s*FEATHERLESS_API_KEY\s*=\s*\S' -Quiet)

# 1. The 50 demo articles (Civil War 1150, Winter War 1256, Mannerheim 6021, ...)
Step "sentence lives: 50 hero articles"     @("pipeline/lives.py", "--heroes", "--workers", "4")
Step "moved sentences"                      @("pipeline/moves.py")
Step "stats (half-life, % deleted)"         @("pipeline/stats.py")

# 2. Coordination scores for every ghost now in the database (reads the Parquet files)
Step "coordination scores"                  @("ai/coordination.py", "--db")

# 3. English for the three demo articles: what readers see first, then the ghosts
if ($hasGemma) {
    foreach ($p in 1150, 1256, 6021) {
        Step "English, living text, page $p"   @("ai/translate.py", "--db", "--page", "$p", "--living")
        Step "English, ghosts, page $p"        @("ai/translate.py", "--db", "--page", "$p", "--ghosts")
    }
} else {
    Write-Host "`n(skipping translations: put FEATHERLESS_API_KEY=... in .env)" -ForegroundColor DarkYellow
}

# 4. Meaning search vectors (needs Modal set up: python -m modal setup, and EMBED_URL in .env)
& python -c "import modal" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "`n>>> embeddings for 1150 (Modal)" -ForegroundColor Yellow
    $t = Measure-Command { & python -m modal run ai/embed_modal.py --db --page 1150 | Out-Host }
    ("{0,-45} {1,8:N1} s" -f "embeddings, page 1150", $t.TotalSeconds) | Add-Content $log
} else {
    Write-Host "`n(skipping embeddings: Modal isn't set up on this laptop)" -ForegroundColor DarkYellow
}

# 5. Optional: every article (the scale number). Already-processed articles are skipped.
if ($All) {
    Step "sentence lives: all 19,742 articles"  @("pipeline/lives.py", "--all", "--workers", "6")
    Step "moved sentences (all)"                @("pipeline/moves.py")
    Step "stats (all)"                          @("pipeline/stats.py")
    Step "coordination scores (all)"            @("ai/coordination.py", "--db")
}

Write-Host "`nDone. Timings:" -ForegroundColor Green
Get-Content $log | Select-Object -Last 20
