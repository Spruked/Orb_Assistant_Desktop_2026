$orbRoot = $PSScriptRoot
$defaultMeshRoot = if (Test-Path "O:\") {
  "O:\orb_mesh"
} elseif (Test-Path "R:\") {
  "R:\orb_mesh"
} else {
  Join-Path $orbRoot "orb_mesh"
}

if (-not $env:ORB_INSTANCE_ID) { $env:ORB_INSTANCE_ID = "desktop" }
if (-not $env:ORB_PRODUCT_NAME) { $env:ORB_PRODUCT_NAME = "Platinum ORB Desktop Assistant" }
if (-not $env:ORB_APP_ID) { $env:ORB_APP_ID = "com.orbs.platinum.desktop" }
if (-not $env:ORB_USER_DATA_DIR) { $env:ORB_USER_DATA_DIR = Join-Path $orbRoot ".orb-assistant-desktop" }
if (-not $env:ORB_SYSTEM_ROOT) { $env:ORB_SYSTEM_ROOT = Join-Path $orbRoot "system" }
if (-not $env:ORB_SHARED_MESH_ROOT) { $env:ORB_SHARED_MESH_ROOT = $defaultMeshRoot }
if (-not $env:ORB_SINGLE_INSTANCE) { $env:ORB_SINGLE_INSTANCE = "1" }
if (-not $env:ORB_PYTHON_PATH) { $env:ORB_PYTHON_PATH = "python" }
if (-not $env:ORB_ENABLE_DESKTOP_PRESENCE) { $env:ORB_ENABLE_DESKTOP_PRESENCE = "1" }
if (-not $env:ORB_ENABLE_BROWSER_AWARENESS) { $env:ORB_ENABLE_BROWSER_AWARENESS = "1" }
if (-not $env:CUDA_VISIBLE_DEVICES) { $env:CUDA_VISIBLE_DEVICES = "0" }
if (-not $env:ORB_LLM_ROUTE) { $env:ORB_LLM_ROUTE = "local" }
if (-not $env:ORB_LOCAL_LLM_ENDPOINT) { $env:ORB_LOCAL_LLM_ENDPOINT = "http://127.0.0.1:11434" }
if (-not $env:ORB_LOCAL_LLM_MODEL) { $env:ORB_LOCAL_LLM_MODEL = "qwen2.5:3b" }
if (-not $env:CALI_OLLAMA_DEVICE) { $env:CALI_OLLAMA_DEVICE = "cuda" }
if (-not $env:CALI_OLLAMA_NUM_GPU) { $env:CALI_OLLAMA_NUM_GPU = "999" }
if (-not $env:CALI_OLLAMA_KEEP_ALIVE) { $env:CALI_OLLAMA_KEEP_ALIVE = "15m" }
if (-not $env:OLLAMA_KEEP_ALIVE) { $env:OLLAMA_KEEP_ALIVE = "15m" }
if (-not $env:OLLAMA_FLASH_ATTENTION) { $env:OLLAMA_FLASH_ATTENTION = "1" }
