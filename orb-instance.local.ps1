$ErrorActionPreference = "Stop"

# Local performance profile for Windows desktop Orb instance.
# This file is loaded by launch_desktop_orb.ps1 after orb-instance.windows.ps1.
# All WSL paths are derived dynamically from this script's drive letter so the
# instance is portable across drive assignments and machines.

# Derive the WSL /mnt/<drive> prefix from whatever drive this repo lives on.
$_drive = ([System.IO.Path]::GetPathRoot($PSScriptRoot)).TrimEnd('\').TrimEnd(':').ToLower()
$_wslMount = "/mnt/$_drive"
$_rootDrive = [System.IO.Path]::GetPathRoot($PSScriptRoot)
$_rootRelative = $PSScriptRoot.Substring($_rootDrive.Length).TrimStart('\') -replace '\\', '/'
$_wslRoot = "$_wslMount/$_rootRelative"
$_substrateRoot = Split-Path -Parent $PSScriptRoot
$_substrateRelative = $_substrateRoot.Substring($_rootDrive.Length).TrimStart('\') -replace '\\', '/'
$_wslSubstrateRoot = "$_wslMount/$_substrateRelative"

# Resolve the WSL home directory at launch time.
$_wslHome = try { (wsl.exe sh -c 'echo $HOME' 2>$null).Trim() } catch { "" }
if (-not $_wslHome) {
    $_wslUser = try { (wsl.exe -- whoami 2>$null).Trim() } catch { "bryan" }
    $_wslHome = "/home/$_wslUser"
}

# Route the Python bridge through Windows Python 3.12. Qwen TTS requires this
# runtime; Ollama remains reachable through the WSL localhost relay.
$env:ORB_PYTHON_PATH = "R:\R_Drive_Substrate\Services\qwen_tts_312\Scripts\python.exe"
$env:ORB_PRODUCT_NAME = "Platinum ORB Desktop Assistant"
$env:ORB_APP_ID = "com.orbs.platinum.desktop"
$env:ORB_DOCK_TIER = "3"

# The active bridge is Windows Python, so use Windows paths for ORB/mesh roots.
$env:ORB_SYSTEM_ROOT = "$PSScriptRoot\system"
$env:ORB_SHARED_MESH_ROOT = "$_substrateRoot\orb_mesh"
$env:ORB_MESH_ROOT = $env:ORB_SHARED_MESH_ROOT
$env:ORB_IDENTITY_PATH = Join-Path $env:ORB_SHARED_MESH_ROOT "identity\bryan_spruk_identity.json"
$env:ORB_DESKTOP_MCP_ROOT = "$PSScriptRoot\mcp\orb_desktop_mcp"
$env:ORB_DESKTOP_MCP_SCRIPT = "$env:ORB_DESKTOP_MCP_ROOT\orb_mcp_server.py"
$env:ORB_DESKTOP_MCP_SHARED_TOOLS = "orb_cognition_review"

# Native faster-whisper hearing runtime. CP3 is not part of the desktop ORB path.
Remove-Item Env:CP3_ROOT -ErrorAction SilentlyContinue
Remove-Item Env:ACP3_ROOT -ErrorAction SilentlyContinue
Remove-Item Env:CP3_SKG_PATH -ErrorAction SilentlyContinue
Remove-Item Env:ACP3_SKG_PATH -ErrorAction SilentlyContinue
Remove-Item Env:CP3_AUDIO_CACHE -ErrorAction SilentlyContinue
Remove-Item Env:ACP3_AUDIO_CACHE -ErrorAction SilentlyContinue

# Kokoro TTS — point at the real ONNX model in WSL.
$env:KOKORO_ENGINE_ROOT = "R:\R_Drive_Substrate\Services\kokoro_engine"
$env:KOKORO_MODEL_PATH = "C:\dev\Desktop\PLATFORM\spruked.com\Orb_Assistant\modules\Adaptive_Cochlear_Processor_v1\kokoro_baseline\assets\kokoro-v1.0.onnx"
$env:KOKORO_VOICES_PATH = "C:\dev\Desktop\PLATFORM\spruked.com\Orb_Assistant\modules\Adaptive_Cochlear_Processor_v1\kokoro_baseline\assets\voices-v1.0.bin"
$env:KOKORO_AUDIO_DIR = "$PSScriptRoot\CALI_System\voice_cache"
$env:KOKORO_ESPEAK_DATA_PATH = ""
$env:KOKORO_ESPEAK_LIB_PATH = ""
$env:KOKORO_DEFAULT_VOICE = "af_bella"
$env:KOKORO_DEFAULT_LANG = "en-us"
$env:KOKORO_ORB_VOICE_MAP_JSON = '{"desktop":"af_bella"}'
$env:ORB_QWEN_TTS_INSTRUCT = "A clear younger adult female voice with a warm, bright, natural tone."
$env:ONNX_PROVIDER = "CUDAExecutionProvider"

# Universal ORB real-time voice is primary and is loaded from:
# R:\R_Drive_Substrate\substrate\orb_universal_config\orb_realtime_voice.env
# Qwen remains preserved for Dandy/show-quality non-real-time generation.
$env:ORB_REALTIME_TTS_ENGINE = "qwen"
$env:ORB_REALTIME_TTS_BASE_URL = "http://127.0.0.1:9880"
$env:ORB_REALTIME_TTS_WS_URL = ""
$env:ORB_REALTIME_TTS_PROTOCOL = "websocket"
$env:ORB_REALTIME_TTS_VOICE = "cali"
$env:ORB_REALTIME_TTS_REQUIRE_READY = "0"
$env:ORB_REALTIME_TTS_CHUNK_SIZE = "5"
$env:ORB_REALTIME_TTS_STREAM_PCM = "1"
$env:ORB_REALTIME_TTS_WRITE_FILES = "0"
$env:ORB_REALTIME_TTS_MODEL = "qwen3-tts-0.6b"
$env:ORB_COSYVOICE_VENV = "venv312"
$env:ORB_COSYVOICE_VENV_PATH = "/home/bryan/venv312"
$env:ORB_REALTIME_STT_ENGINE = "faster-whisper"
$env:ORB_REALTIME_STT_PYTHON = "/home/bryan/venv312/bin/python"
$env:ORB_REALTIME_STT_MODULE = "faster_whisper"
$env:ORB_REALTIME_STT_PACKAGE_VERSION = "1.2.1"
$env:ORB_REALTIME_STT_ALLOW_OPENAI_WHISPER = "0"
$env:ORB_VOICE_PACK_NAME = "cali"
$env:ORB_VOICE_PACK_DIR = "R:\R_Drive_Substrate\substrate\orb_voice\voice_packs\cali"
$env:ORB_VOICE_PRESENCE_DIR = "R:\R_Drive_Substrate\substrate\orb_voice\voice_packs\cali\presence"
$env:ORB_VOICE_REFERENCE_AUDIO = "R:\R_Drive_Substrate\substrate\orb_voice\voice_packs\cali\reference\cali_reference.wav"
$env:ORB_VOICE_PRESENCE_ENABLED = "1"
$env:ORB_QWEN_TTS_ENDPOINT = "http://127.0.0.1:9880"
$env:ORB_QWEN_TTS_FALLBACK_ENDPOINT = "http://127.0.0.1:8020"
$env:ORB_QWEN_TTS_TIMEOUT_SEC = "120"
$env:ORB_REALTIME_TTS_TIMEOUT_SEC = "120"
$env:DANDY_QWEN_BACKENDS = "http://127.0.0.1:8031,http://127.0.0.1:8032,http://127.0.0.1:8033"
$env:QWEN_TTS_URL = "http://127.0.0.1:9880/synthesize"

# GPU / renderer settings.
$env:CUDA_VISIBLE_DEVICES = "0"
$env:CALI_OLLAMA_DEVICE = "cuda"
$env:CALI_OLLAMA_NUM_GPU = "999"
$env:CALI_OLLAMA_KEEP_ALIVE = "15m"
$env:OLLAMA_KEEP_ALIVE = "15m"
$env:OLLAMA_FLASH_ATTENTION = "1"
$env:ORB_USE_GL = "angle"
$env:ORB_USE_ANGLE = "d3d11"
$env:ORB_IGNORE_GPU_BLOCKLIST = "1"
$env:ORB_ENABLE_GPU_RASTERIZATION = "1"

# Reduce renderer + bridge load.
$env:ORB_PRIMARY_DISPLAY_ONLY = "0"
$env:ORB_SINGLE_ORB_MULTI_DISPLAY = "1"
$env:ORB_START_DOCKED = "0"
$env:ORB_DESKTOP_CURSOR_BEHAVIOR = "1"
$env:ORB_MULTI_DISPLAY_PATROL = "1"
$env:ORB_MULTI_DISPLAY_PATROL_INTERVAL_MS = "3500"
$env:ORB_MULTI_DISPLAY_PATROL_SPEED_BONUS = "2.4"
$env:ORB_CURSOR_SAMPLE_MS = "33"
$env:ORB_TOPMOST_WATCHDOG_MS = "500"
$env:ORB_TOPMOST_REFRESH_MS = "3000"
$env:ORB_CURSOR_CLEARANCE_EXTRA_PX = "70"
$env:ORB_CALM_SCREEN_ANCHOR = "1"
$env:ORB_SCREEN_ANCHOR_X_RATIO = "0.54"
$env:ORB_SCREEN_ANCHOR_Y_RATIO = "0.44"
$env:ORB_CURSOR_FOLLOW = "1"
$env:ORB_CURSOR_FOLLOW_ENABLED = "1"
$env:ORB_CURSOR_ATTRACTION_STRENGTH = "0.08"
$env:ORB_CURSOR_ASSIST_MODE_ONLY = "1"
$env:ORB_CURSOR_AVAILABILITY_ENABLED = "1"
$env:ORB_CURSOR_AVAILABILITY_DISTANCE = "1700"
$env:ORB_CURSOR_AVAILABILITY_COOLDOWN_MS = "8000"
$env:ORB_CURSOR_FOLLOW_OFFSET_X = "18"
$env:ORB_CURSOR_FOLLOW_OFFSET_Y = "16"
$env:ORB_CURSOR_FOLLOW_LERP = "0.07"
$env:ORB_CURSOR_REANCHOR_DISTANCE = "520"
$env:ORB_CURSOR_REANCHOR_SETTLE_DISTANCE = "80"
$env:ORB_MAX_ACCELERATION = "0.18"
$env:ORB_MOVEMENT_SMOOTHING = "0.68"
$env:ORB_SCREEN_EDGE_PADDING = "96"
$env:ORB_COMPANION_MODE = "1"
$env:ORB_COMPANION_BOND_RADIUS = "620"
$env:ORB_COMPANION_RETURN_DISTANCE = "1400"
$env:ORB_COMPANION_USER_ACTIVE_MS = "1800"
$env:ORB_IDLE_SLEEP_AFTER_MS = "90000"
$env:ORB_PLAYFUL_IDLE_ENABLED = "1"
$env:ORB_PLAYFUL_IDLE_INTERVAL_MS = "24000"
$env:ORB_PLAYFUL_IDLE_DURATION_MS = "3200"
$env:ORB_OPEN_DOCK_ON_START = "1"
$env:ORB_LAUNCH_GREETING_ENABLED = "0"

# Reduce optional background workloads in the Python bridge.
$env:ORB_ENABLE_DESKTOP_PRESENCE = "0"
$env:ORB_ENABLE_BROWSER_AWARENESS = "1"
$env:ORB_ENABLE_SWARM_EXTENSION = "0"
$env:ORB_PRELOAD_AUDIO_RUNTIME = "1"
$env:ORB_ENABLE_CP3_TEXT_FRAME = "0"
$env:ORB_AUTO_LISTEN = "1"

$env:ORB_AUDIO_BACKEND = "auto"
$env:ORB_TTS_PROVIDER = "qwen"
$env:ORB_PRIMARY_TTS_PROVIDER = "qwen"
$env:ORB_ENABLE_KOKORO_FALLBACK = "1"
$env:ACP_WHISPER_DEVICE = "auto"
$env:ACP_WHISPER_BACKEND = "faster-whisper"
$env:WHISPER_BACKEND = "faster-whisper"
$env:FASTER_WHISPER_DEVICE = "cpu"
$env:FASTER_WHISPER_COMPUTE_TYPE = "int8"

# Default governed local LLM route through Ollama.
$env:ORB_LLM_ROUTE = "local"
$env:ORB_LOCAL_LLM_ENDPOINT = "http://127.0.0.1:11434"
$env:ORB_LOCAL_LLM_MODEL = "llama3.2:1b"
$env:ORB_LLM_ENDPOINT = $env:ORB_LOCAL_LLM_ENDPOINT
$env:ORB_LLM_MODEL = $env:ORB_LOCAL_LLM_MODEL
$env:ORB_LLM_GOVERNANCE_WRAPPER = "0"
$env:ORB_LLM_RETAIN_VOICE = "1"
$env:ORB_CRM_DB_PATH = "R:/R_Drive_Substrate/crm/memory/cali_personal.db"
$env:ORB_EMAIL_DB_PATH = "R:/email_client/emails.db"
$env:ORB_CRM_API_URL = "http://127.0.0.1:21000"
$env:ORB_EMAIL_API_URL = "http://127.0.0.1:19000/api"
if (-not $env:ORB_ADMIN_TOKEN -and $env:CALI_ADMIN_TOKEN) { $env:ORB_ADMIN_TOKEN = $env:CALI_ADMIN_TOKEN }
$env:ORB_API_HOST = "127.0.0.1"
$env:ORB_API_PORT = "21100"
$env:ORB_API_URL = "http://127.0.0.1:21100/api/v1"

# Constrain CPU-heavy native math thread pools.
$env:OMP_NUM_THREADS = "4"
$env:MKL_NUM_THREADS = "4"
$env:OPENBLAS_NUM_THREADS = "4"
$env:NUMEXPR_MAX_THREADS = "4"
$env:UV_THREADPOOL_SIZE = "4"
