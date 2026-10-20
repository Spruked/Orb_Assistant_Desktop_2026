$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "orb_qwen_code_env.ps1")

Write-Host "[ORB/QwenCode] Using $env:OPENAI_BASE_URL"
Write-Host "[ORB/QwenCode] Model $env:OPENAI_MODEL"
Write-Host "[ORB/QwenCode] Type in this terminal when Qwen Code opens. Close the terminal to stop it."

& node $env:ORB_QWEN_CODE_ENTRYPOINT --auth-type $env:ORB_QWEN_CODE_AUTH_TYPE --model $env:ORB_QWEN_CODE_MODEL
