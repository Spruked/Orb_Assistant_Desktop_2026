$orbRoot = $PSScriptRoot
$substrateRoot = Split-Path -Parent $orbRoot
$defaultMeshRoot = if (Test-Path "O:\") {
  "O:\orb_mesh"
} elseif (Test-Path "R:\") {
  Join-Path $substrateRoot "orb_mesh"
} else {
  Join-Path $orbRoot "orb_mesh"
}

if (-not $env:ORB_INSTANCE_ID) { $env:ORB_INSTANCE_ID = "desktop" }
if (-not $env:ORB_PRODUCT_NAME) { $env:ORB_PRODUCT_NAME = "Platinum ORB Desktop Assistant" }
if (-not $env:ORB_APP_ID) { $env:ORB_APP_ID = "com.orbs.platinum.desktop" }
if (-not $env:ORB_USER_DATA_DIR) { $env:ORB_USER_DATA_DIR = Join-Path $orbRoot ".orb-assistant-desktop" }
if (-not $env:ORB_SYSTEM_ROOT) { $env:ORB_SYSTEM_ROOT = Join-Path $orbRoot "system" }
if (-not $env:ORB_SHARED_MESH_ROOT) { $env:ORB_SHARED_MESH_ROOT = $defaultMeshRoot }
if (-not $env:ORB_MESH_ROOT) { $env:ORB_MESH_ROOT = $env:ORB_SHARED_MESH_ROOT }
if (-not $env:ORB_IDENTITY_PATH) { $env:ORB_IDENTITY_PATH = Join-Path $env:ORB_SHARED_MESH_ROOT "identity\bryan_spruk_identity.json" }
if (-not $env:ORB_DESKTOP_MCP_ROOT) { $env:ORB_DESKTOP_MCP_ROOT = Join-Path $orbRoot "mcp\orb_desktop_mcp" }
if (-not $env:ORB_DESKTOP_MCP_SCRIPT) { $env:ORB_DESKTOP_MCP_SCRIPT = Join-Path $env:ORB_DESKTOP_MCP_ROOT "orb_mcp_server.py" }
if (-not $env:ORB_DESKTOP_MCP_SHARED_TOOLS) { $env:ORB_DESKTOP_MCP_SHARED_TOOLS = "orb_cognition_review" }
if (-not $env:ORB_REALTIME_STT_ENGINE) { $env:ORB_REALTIME_STT_ENGINE = "faster-whisper" }
if (-not $env:ORB_REALTIME_STT_PYTHON) { $env:ORB_REALTIME_STT_PYTHON = "/home/bryan/venv312/bin/python" }
if (-not $env:ORB_REALTIME_STT_MODULE) { $env:ORB_REALTIME_STT_MODULE = "faster_whisper" }
if (-not $env:ORB_SINGLE_INSTANCE) { $env:ORB_SINGLE_INSTANCE = "1" }
if (-not $env:ORB_PYTHON_PATH) { $env:ORB_PYTHON_PATH = "python" }
if (-not $env:ORB_ENABLE_DESKTOP_PRESENCE) { $env:ORB_ENABLE_DESKTOP_PRESENCE = "1" }
if (-not $env:ORB_ENABLE_BROWSER_AWARENESS) { $env:ORB_ENABLE_BROWSER_AWARENESS = "1" }
if (-not $env:CUDA_VISIBLE_DEVICES) { $env:CUDA_VISIBLE_DEVICES = "0" }
if (-not $env:ORB_LLM_ROUTE) { $env:ORB_LLM_ROUTE = "local" }
if (-not $env:ORB_LOCAL_LLM_ENDPOINT) { $env:ORB_LOCAL_LLM_ENDPOINT = "http://127.0.0.1:11434" }
if (-not $env:ORB_LOCAL_LLM_MODEL) { $env:ORB_LOCAL_LLM_MODEL = "llama3.2:1b" }
if (-not $env:ORB_CRM_DB_PATH) { $env:ORB_CRM_DB_PATH = "R:/R_Drive_Substrate/crm/memory/cali_personal.db" }
if (-not $env:ORB_EMAIL_DB_PATH) { $env:ORB_EMAIL_DB_PATH = "R:/email_client/emails.db" }
if (-not $env:ORB_CRM_API_URL) { $env:ORB_CRM_API_URL = "http://127.0.0.1:21000" }
if (-not $env:ORB_EMAIL_API_URL) { $env:ORB_EMAIL_API_URL = "http://127.0.0.1:19000/api" }
if (-not $env:ORB_ADMIN_TOKEN -and $env:CALI_ADMIN_TOKEN) { $env:ORB_ADMIN_TOKEN = $env:CALI_ADMIN_TOKEN }
if (-not $env:ORB_API_HOST) { $env:ORB_API_HOST = "127.0.0.1" }
if (-not $env:ORB_API_PORT) { $env:ORB_API_PORT = "21100" }
if (-not $env:ORB_API_URL) { $env:ORB_API_URL = "http://127.0.0.1:21100/api/v1" }
if (-not $env:CALI_OLLAMA_DEVICE) { $env:CALI_OLLAMA_DEVICE = "cuda" }
if (-not $env:CALI_OLLAMA_NUM_GPU) { $env:CALI_OLLAMA_NUM_GPU = "999" }
if (-not $env:CALI_OLLAMA_KEEP_ALIVE) { $env:CALI_OLLAMA_KEEP_ALIVE = "15m" }
if (-not $env:OLLAMA_KEEP_ALIVE) { $env:OLLAMA_KEEP_ALIVE = "15m" }
if (-not $env:OLLAMA_FLASH_ATTENTION) { $env:OLLAMA_FLASH_ATTENTION = "1" }
