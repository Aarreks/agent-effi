$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
  $uv=Get-Command uv -ErrorAction SilentlyContinue
  $localUv=Join-Path (Split-Path $PSScriptRoot -Parent) '.venv\Scripts\uv.exe'
  if($uv){$uvExecutable=$uv.Source}elseif(Test-Path -LiteralPath $localUv){$uvExecutable=$localUv}else{throw 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/'}
  & $uvExecutable sync --frozen
  if($LASTEXITCODE -ne 0){throw 'Python dependency installation failed'}
  Push-Location frontend
  try{
    $bundledNodeBin=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin'
    $previousPath=$env:PATH
    if(Test-Path -LiteralPath (Join-Path $bundledNodeBin 'node.exe')){$env:PATH="$bundledNodeBin;$env:PATH"}
    try{
      node -e "const [major,minor]=process.versions.node.split('.').map(Number); if(major<22||(major===22&&minor<22)){console.error('Node 22.22 or newer is required');process.exit(1)}"
      if($LASTEXITCODE -ne 0){throw 'Update Node before installing frontend dependencies'}
      $npmLauncher=(Get-Command npm -ErrorAction Stop).Source
      $npmCli=Join-Path (Split-Path $npmLauncher -Parent) 'node_modules\npm\bin\npm-cli.js'
      if(Test-Path -LiteralPath $npmCli){& (Get-Command node).Source $npmCli ci --no-audit --no-fund}else{npm ci --no-audit --no-fund}
      if($LASTEXITCODE -ne 0){throw 'Frontend dependency installation failed'}
    }finally{$env:PATH=$previousPath}
  }finally{Pop-Location}
  New-Item -ItemType Directory -Force data,tools/livekit | Out-Null
  if(-not(Test-Path -LiteralPath .env)){Copy-Item .env.example .env}
  & .\.venv\Scripts\python.exe tools\configure_auth.py
  if($LASTEXITCODE -ne 0){throw 'Local access configuration failed'}
  if(-not(Test-Path -LiteralPath tools/livekit/livekit-server.exe)){
    Invoke-WebRequest 'https://github.com/livekit/livekit/releases/download/v1.13.7/livekit_1.13.7_windows_amd64.zip' -OutFile tools/livekit.zip
    Expand-Archive -LiteralPath tools/livekit.zip -DestinationPath tools/livekit -Force
  }
  Write-Host 'Ready. Configure LiveKit Cloud credentials in .env, then run .\run.ps1. README.md also describes the direct OpenAI alternative.'
}finally{Pop-Location}
