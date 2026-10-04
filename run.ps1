param([int]$ApiPort=8060,[int]$WebPort=3060)
$ErrorActionPreference='Stop'
$projectRoot=$PSScriptRoot
$python=Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run setup.ps1 first.' }
& $python (Join-Path $projectRoot 'tools\configure_auth.py')
if($LASTEXITCODE -ne 0){throw 'Local access configuration failed'}
$bundledNode=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
$node=if(Test-Path -LiteralPath $bundledNode){$bundledNode}else{(Get-Command node -ErrorAction Stop).Source}
foreach($port in @($ApiPort,$WebPort)){
  if(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue){throw "Port $port is occupied. Stop the existing app or choose another port."}
}
$children=@()
$oldBackend=$env:BACKEND_URL
$oldSocket=$env:NEXT_PUBLIC_WS_URL
$oldOrigin=$env:FRONTEND_ORIGIN
function Stop-OwnedProcessTree([int]$ProcessId) {
  Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue | ForEach-Object {Stop-OwnedProcessTree $_.ProcessId}
  Stop-Process -Id $ProcessId -ErrorAction SilentlyContinue
}
try {
  $env:BACKEND_URL="http://127.0.0.1:$ApiPort"
  $env:NEXT_PUBLIC_WS_URL="ws://127.0.0.1:$ApiPort/events"
  $env:FRONTEND_ORIGIN="http://127.0.0.1:$WebPort"
  $children+=Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',"$ApiPort") -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'data\api.log') -RedirectStandardError (Join-Path $projectRoot 'data\api-error.log')
  $ready=$false
  for($i=0;$i -lt 40;$i++) {
    try{$health=Invoke-RestMethod "$env:BACKEND_URL/health"; $ready=$true;break}catch{Start-Sleep -Milliseconds 500}
  }
  if(-not$ready){throw 'Backend did not start. See data/api-error.log.'}
  if ($health.livekit_url -match '^ws://(127\.0\.0\.1|localhost):7880' -and -not (Get-NetTCPConnection -LocalPort 7880 -State Listen -ErrorAction SilentlyContinue)) {
    $server=Join-Path $projectRoot 'tools\livekit\livekit-server.exe'
    if(-not(Test-Path -LiteralPath $server)){throw 'Local LiveKit server missing. Run setup.ps1.'}
    $children+=Start-Process -FilePath $server -ArgumentList @('--dev','--bind','127.0.0.1','--node-ip','127.0.0.1') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'data\livekit.log') -RedirectStandardError (Join-Path $projectRoot 'data\livekit-error.log')
  }
  if($health.voice_configured){
    $children+=Start-Process -FilePath $python -ArgumentList @('-m','backend.agent','dev') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'data\agent.log') -RedirectStandardError (Join-Path $projectRoot 'data\agent-error.log')
  }else{Write-Host 'Voice unavailable: connect LiveKit Cloud or add OPENAI_API_KEY to submission/.env and restart.' -ForegroundColor Yellow}
  Write-Host "EffiGov Voice Desk: http://127.0.0.1:$WebPort · Ctrl+C stops this run."
  Push-Location (Join-Path $projectRoot 'frontend')
  try { & $node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port $WebPort } finally {Pop-Location}
} finally {
  foreach($child in $children){if(-not$child.HasExited){Stop-OwnedProcessTree $child.Id}}
  $env:BACKEND_URL=$oldBackend
  $env:NEXT_PUBLIC_WS_URL=$oldSocket
  $env:FRONTEND_ORIGIN=$oldOrigin
}
