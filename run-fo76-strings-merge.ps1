param(
    [string]$ToolsRoot = "F:\games\fallout76 tools",
    [string]$GameData = "H:\XboxGames\Fallout 76\Content\Data",
    [string]$RatZip = "",
    [string]$QuizzlessSst = "",
    [switch]$DryRun,
    [switch]$KeepTemp
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonScript = Join-Path $ScriptDir "fo76_strings_merge.py"

if (-not (Test-Path -LiteralPath $PythonScript)) {
    throw "Cannot find $PythonScript"
}

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
    throw "Python was not found on PATH."
}

$argsList = @(
    $PythonScript,
    "--tools-root", $ToolsRoot,
    "--game-data", $GameData
)

if ($RatZip) {
    $argsList += @("--rat-zip", $RatZip)
}
if ($QuizzlessSst) {
    $argsList += @("--quizzless-sst", $QuizzlessSst)
}
if ($DryRun) {
    $argsList += "--dry-run"
}
if ($KeepTemp) {
    $argsList += "--keep-temp"
}

if ($pythonCmd.Name -eq "py.exe" -or $pythonCmd.Name -eq "py") {
    & $pythonCmd.Source -3 @argsList
} else {
    & $pythonCmd.Source @argsList
}

if ($LASTEXITCODE -ne 0) {
    throw "Merge failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Done. Review the JSON summary above." -ForegroundColor Green
