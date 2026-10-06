# Starts the demo server in the background on http://127.0.0.1:5070 (localhost only).
$root = Split-Path -Parent $PSScriptRoot
$port = 5070
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) { Write-Output 'Python tapılmadı'; exit 1 }
$logs = Join-Path $root 'logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($existing) { Write-Output "ALREADY_RUNNING pid=$($existing[0].OwningProcess) http://127.0.0.1:$port"; exit 0 }
$out = Join-Path $logs 'server.out.log'
$err = Join-Path $logs 'server.err.log'
$arg = "/c cd /d `"$root`" && `"$py`" run.py --port $port 1>`"$out`" 2>`"$err`""
Start-Process cmd.exe -ArgumentList $arg -WindowStyle Hidden | Out-Null
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 250
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { Write-Output "STARTED http://127.0.0.1:$port"; exit 0 }
}
Write-Output 'FAILED_TO_START'
if (Test-Path $err) { Get-Content $err -Tail 40 }
exit 1
