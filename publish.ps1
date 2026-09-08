# Optional command-line shortcut. Normal use: Start.cmd > Publish to GitHub.
Set-Location -Path $PSScriptRoot
$travelPython = if (Test-Path '.venv\Scripts\python.exe') { '.venv\Scripts\python.exe' } else { 'python' }
& $travelPython scripts\publish.py
$travelExit = $LASTEXITCODE
Read-Host 'Press Enter to close'
exit $travelExit
