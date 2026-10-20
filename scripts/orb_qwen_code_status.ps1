$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "orb_qwen_code_env.ps1")

Write-Host "[ORB/QwenCode] base: $env:OPENAI_BASE_URL"
Write-Host "[ORB/QwenCode] model: $env:OPENAI_MODEL"

$models = Invoke-RestMethod -Uri "$env:ORB_LOCAL_LLM_ENDPOINT/v1/models" -TimeoutSec 8
$modelIds = @()
if ($models.data) {
  $modelIds = @($models.data | ForEach-Object { $_.id })
} elseif ($models.models) {
  $modelIds = @($models.models | ForEach-Object { $_.model })
}

Write-Host "[llama.cpp] models:"
$modelIds | ForEach-Object { Write-Host "  $_" }

$body = @{
  model = $env:ORB_LOCAL_LLM_MODEL
  messages = @(@{ role = "user"; content = "Reply with exactly: ORB VS Code Qwen Code ok" })
  max_tokens = 16
  temperature = 0
} | ConvertTo-Json -Depth 8

$chat = Invoke-RestMethod -Uri "$env:ORB_LOCAL_LLM_ENDPOINT/v1/chat/completions" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 30
$reply = [string]$chat.choices[0].message.content
Write-Host "[llama.cpp] chat: $reply"

$version = & node $env:ORB_QWEN_CODE_ENTRYPOINT --version
Write-Host "[QwenCode] version: $version"
Write-Host "[QwenCode] ready for VS Code terminal use."
