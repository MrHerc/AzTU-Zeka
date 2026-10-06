# Stops the demo server listening on port 5070.
$c = Get-NetTCPConnection -LocalPort 5070 -State Listen -ErrorAction SilentlyContinue
if ($c) { $c | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; Write-Output 'STOPPED' } else { Write-Output 'NOT_RUNNING' }
