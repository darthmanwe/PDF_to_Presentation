<#
.SYNOPSIS
    Build the pdfdeck no-install Windows app (PyInstaller one-dir), inject the
    developer's API keys, self-test the frozen exe, and produce a shippable zip.

.DESCRIPTION
    Reuses the project .venv (it already holds the exact validated dependency
    set). Real API keys are read from the repo .env and written ONLY into the
    gitignored dist/ output -- they never enter git. LANGSMITH_* is never
    shipped.

.PARAMETER Console
    Build a console variant (shows a terminal + traceback) for diagnosing a
    missing-module problem. Ship the default (windowed) build.

.PARAMETER SkipSmoke
    Skip the frozen --selftest step (not recommended).

.EXAMPLE
    .\packaging\build.ps1
    .\packaging\build.ps1 -Console
#>
[CmdletBinding()]
param(
    [switch]$Console,
    [switch]$SkipSmoke
)

$ErrorActionPreference = 'Stop'

$pkgDir     = $PSScriptRoot
$repo       = Split-Path $pkgDir -Parent
$py         = Join-Path $repo '.venv\Scripts\python.exe'
$spec       = Join-Path $pkgDir 'pdfdeck_gui.spec'
$template   = Join-Path $pkgDir 'config.template.txt'
$readme     = Join-Path $pkgDir 'README_FIRST.txt'
$distRoot   = Join-Path $pkgDir 'dist'
$workRoot   = Join-Path $pkgDir 'build'
$distFolder = Join-Path $distRoot 'pdfdeck-2.0.0'
$envFile    = Join-Path $repo '.env'

Write-Host "=== pdfdeck build ===" -ForegroundColor Cyan
Write-Host "repo: $repo"

if (-not (Test-Path $py)) { throw "venv python not found at $py -- create .venv first." }
if (-not (Test-Path $spec)) { throw "spec not found at $spec" }

# Native tools (pip, PyInstaller) log to stderr. Under $ErrorActionPreference
# = 'Stop', PowerShell can turn that stderr into a terminating error when the
# output is redirected/merged. Run native commands under 'Continue' and gate on
# $LASTEXITCODE instead, so the build is robust however it is invoked.
function Invoke-Native {
    param([Parameter(Mandatory)][scriptblock]$Cmd, [string]$What)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $Cmd
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($code -ne 0) { throw "$What failed (exit $code)" }
}

# --- 1) build tooling (into the venv; not a runtime dependency) -----------
Write-Host "`n[1/6] Ensuring PyInstaller is installed..." -ForegroundColor Yellow
Invoke-Native -What "pip install pyinstaller" -Cmd { & $py -m pip install "pyinstaller>=6.10" }

# --- 2) clean + run PyInstaller ------------------------------------------
Write-Host "`n[2/6] Cleaning previous output..." -ForegroundColor Yellow
foreach ($d in @($distRoot, $workRoot)) {
    if (Test-Path $d) { Remove-Item -Recurse -Force $d }
}

if ($Console) {
    $env:PDFDECK_CONSOLE = '1'
    Write-Host "  (console diagnostic build)"
} else {
    Remove-Item Env:\PDFDECK_CONSOLE -ErrorAction SilentlyContinue
}

Write-Host "`n[3/6] Running PyInstaller (this takes a few minutes)..." -ForegroundColor Yellow
Invoke-Native -What "PyInstaller" -Cmd {
    & $py -m PyInstaller $spec --noconfirm --distpath $distRoot --workpath $workRoot
}
if (-not (Test-Path $distFolder)) { throw "expected output folder missing: $distFolder" }

# --- 3) inject keys from .env into the shipped config file ----------------
Write-Host "`n[4/6] Injecting keys into pdfdeck.config.txt..." -ForegroundColor Yellow
if (-not (Test-Path $envFile)) { throw ".env not found at $envFile -- cannot inject keys." }

$envMap = @{}
foreach ($line in Get-Content $envFile) {
    $t = $line.Trim()
    if ($t -eq '' -or $t.StartsWith('#')) { continue }
    $idx = $t.IndexOf('=')
    if ($idx -lt 1) { continue }
    $k = $t.Substring(0, $idx).Trim()
    $v = $t.Substring($idx + 1).Trim()
    if ($v.Length -ge 2 -and
        (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'")))) {
        $v = $v.Substring(1, $v.Length - 2)
    }
    $envMap[$k] = $v
}

if (-not $envMap.ContainsKey('ANTHROPIC_API_KEY') -or [string]::IsNullOrWhiteSpace($envMap['ANTHROPIC_API_KEY'])) {
    throw "ANTHROPIC_API_KEY missing or empty in $envFile -- refusing to ship a keyless build."
}

$coreKeys  = @('ANTHROPIC_API_KEY', 'AZURE_TRANSLATOR_KEY', 'AZURE_TRANSLATOR_ENDPOINT', 'AZURE_TRANSLATOR_REGION')
$modelKeys = @('VISION_MODEL', 'CONTENT_MODEL', 'CRITIC_MODEL', 'FALLBACK_MODEL')

$lines = @(
    '# pdfdeck ayar dosyasi -- BU DOSYAYI SILMEYIN.',
    '# pdfdeck settings file -- DO NOT DELETE THIS FILE.',
    ''
)
foreach ($k in $coreKeys) {
    $val = ''
    if ($envMap.ContainsKey($k)) { $val = $envMap[$k] }
    $lines += "$k=$val"
}
foreach ($k in $modelKeys) {
    if ($envMap.ContainsKey($k) -and -not [string]::IsNullOrWhiteSpace($envMap[$k])) {
        $lines += "$k=$($envMap[$k])"
    }
}

$configOut = Join-Path $distFolder 'pdfdeck.config.txt'
Set-Content -Path $configOut -Value $lines -Encoding utf8

$azure = -not [string]::IsNullOrWhiteSpace($envMap['AZURE_TRANSLATOR_KEY'])
Write-Host ("  config written (Anthropic: yes, Azure Translator: {0})" -f ($(if ($azure) { 'yes' } else { 'NO -> Turkish will fall back to English' })))

Copy-Item $readme (Join-Path $distFolder 'README_FIRST.txt') -Force

# --- 4) smoke test the frozen exe ----------------------------------------
$exe = Join-Path $distFolder 'PDFDeck.exe'
if (-not (Test-Path $exe)) { throw "PDFDeck.exe not found in $distFolder" }

if (-not $SkipSmoke) {
    Write-Host "`n[5/6] Self-testing the frozen exe (--selftest)..." -ForegroundColor Yellow
    $p = Start-Process -FilePath $exe -ArgumentList '--selftest' -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        throw "Frozen --selftest FAILED (exit $($p.ExitCode)). Read %LOCALAPPDATA%\pdfdeck\logs\pdfdeck.log, then add the missing module to hiddenimports/copy_metadata in the spec and rebuild."
    }
    Write-Host "  self-test OK" -ForegroundColor Green
} else {
    Write-Host "`n[5/6] Skipping smoke test (-SkipSmoke)." -ForegroundColor DarkYellow
}

# --- 5) zip + report ------------------------------------------------------
Write-Host "`n[6/6] Zipping..." -ForegroundColor Yellow
$zip = Join-Path $distRoot 'pdfdeck-2.0.0-win64.zip'
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $distFolder -DestinationPath $zip

$item   = Get-Item $zip
$sizeMB = [math]::Round($item.Length / 1MB, 1)
$hash   = (Get-FileHash -Algorithm SHA256 $zip).Hash

Write-Host "`n=== DONE ===" -ForegroundColor Green
Write-Host "Zip:    $zip"
Write-Host "Size:   $sizeMB MB"
Write-Host "SHA256: $hash"
Write-Host "`nHand this zip to Dad. He extracts it and double-clicks PDFDeck.exe."
