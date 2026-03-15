# PaperTalker-CLI - Setup Wrapper
Set-Location $PSScriptRoot
Write-Host ""
Write-Host "PaperTalker-CLI - Starting installation..." -ForegroundColor Cyan
Write-Host ""
$batPath = Join-Path $PSScriptRoot "setup.bat"
& cmd.exe /c $batPath
