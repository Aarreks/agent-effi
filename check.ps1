$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
  & .\.venv\Scripts\python.exe -m pytest tests -q
  if($LASTEXITCODE -ne 0){throw 'Backend tests failed'}
  $bundledNode=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
  $node=if(Test-Path -LiteralPath $bundledNode){$bundledNode}else{(Get-Command node).Source}
  Push-Location frontend
  try{
    if(Test-Path -LiteralPath .next){Get-ChildItem -LiteralPath .next -Recurse -Force | ForEach-Object {if($_.Attributes -band [IO.FileAttributes]::ReadOnly){$_.Attributes=$_.Attributes -band (-bnot [IO.FileAttributes]::ReadOnly)}}}
    & $node node_modules/next/dist/bin/next build
    if($LASTEXITCODE -ne 0){throw 'Frontend production build failed'}
  }finally{Pop-Location}
}finally{Pop-Location}
