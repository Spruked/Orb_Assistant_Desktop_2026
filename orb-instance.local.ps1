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

# CP3 adapter root and audio cache. Qwen is primary; Kokoro is fallback.
$env:CP3_ROOT = "C:\dev\Desktop\cochlear_processor_3.0"
$env:CP3_SKG_PATH = "$PSScriptRoot\system\CALI_System\memory\hearing_skg_v3.json"
$env:CP3_AUDIO_CACHE = "$PSScriptRoot\CALI_System\voice_cache"

# Kokoro TTS — point at the real ONNX model in WSL.
$env:KOKORO_MODEL_PATH = "C:\dev\Desktop\PLATFORM\spruked.com\Orb_Assistant\modules\Adaptive_Cochlear_Processor_v1\kokoro_baseline\assets\kokoro-v1.0.onnx"
$env:KOKORO_VOICES_PATH = "C:\dev\Desktop\PLATFORM\spruked.com\Orb_Assistant\modules\Adaptive_Cochlear_Processor_v1\kokoro_baseline\assets\voices-v1.0.bin"
$env:KOKORO_AUDIO_DIR = "$PSScriptRoot\CALI_System\voice_cache"
$env:KOKORO_ESPEAK_DATA_PATH = ""
$env:KOKORO_ESPEAK_LIB_PATH = ""
$env:KOKORO_DEFAULT_VOICE = "af_sky"
$env:KOKORO_DEFAULT_LANG = "en-us"
$env:KOKORO_ORB_VOICE_MAP_JSON = '{"desktop":"af_sky"}'
$env:ONNX_PROVIDER = "CUDAExecutionProvider"

# Qwen TTS bridge is primary. Kokoro remains fallback-only inside runtime.
$env:ORB_QWEN_TTS_ENDPOINT = "http://127.0.0.1:8020"
$env:DANDY_QWEN_BACKENDS = "http://127.0.0.1:8031,http://127.0.0.1:8032,http://127.0.0.1:8033"
$env:QWEN_TTS_URL = "http://127.0.0.1:8020/synthesize"

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
$env:ORB_MULTI_DISPLAY_PATROL = "0"
$env:ORB_MULTI_DISPLAY_PATROL_INTERVAL_MS = "8500"
$env:ORB_MULTI_DISPLAY_PATROL_SPEED_BONUS = "1.15"
$env:ORB_CURSOR_SAMPLE_MS = "33"
$env:ORB_TOPMOST_WATCHDOG_MS = "500"
$env:ORB_TOPMOST_REFRESH_MS = "3000"
$env:ORB_CURSOR_CLEARANCE_EXTRA_PX = "140"
$env:ORB_CALM_SCREEN_ANCHOR = "1"
$env:ORB_SCREEN_ANCHOR_X_RATIO = "0.68"
$env:ORB_SCREEN_ANCHOR_Y_RATIO = "0.36"
$env:ORB_CURSOR_FOLLOW = "1"
$env:ORB_CURSOR_FOLLOW_OFFSET_X = "120"
$env:ORB_CURSOR_FOLLOW_OFFSET_Y = "-90"
$env:ORB_CURSOR_FOLLOW_LERP = "0.026"
$env:ORB_CURSOR_REANCHOR_DISTANCE = "960"
$env:ORB_CURSOR_REANCHOR_SETTLE_DISTANCE = "140"
$env:ORB_COMPANION_MODE = "1"
$env:ORB_COMPANION_BOND_RADIUS = "420"
$env:ORB_COMPANION_RETURN_DISTANCE = "980"
$env:ORB_COMPANION_USER_ACTIVE_MS = "1800"
$env:ORB_PLAYFUL_IDLE_ENABLED = "1"
$env:ORB_PLAYFUL_IDLE_INTERVAL_MS = "24000"
$env:ORB_PLAYFUL_IDLE_DURATION_MS = "3200"
$env:ORB_OPEN_DOCK_ON_START = "1"

# Reduce optional background workloads in the Python bridge.
$env:ORB_ENABLE_DESKTOP_PRESENCE = "0"
$env:ORB_ENABLE_BROWSER_AWARENESS = "1"
$env:ORB_ENABLE_SWARM_EXTENSION = "0"
$env:ORB_PRELOAD_AUDIO_RUNTIME = "1"
$env:ORB_ENABLE_CP3_TEXT_FRAME = "1"
$env:ORB_AUTO_LISTEN = "0"

$env:ORB_AUDIO_BACKEND = "auto"
$env:ACP_WHISPER_DEVICE = "auto"

# Default governed local LLM route through Ollama.
$env:ORB_LLM_ROUTE = "local"
$env:ORB_LOCAL_LLM_ENDPOINT = "http://127.0.0.1:11434"
$env:ORB_LOCAL_LLM_MODEL = "qwen2.5:3b"
$env:ORB_LLM_GOVERNANCE_WRAPPER = "1"
$env:ORB_LLM_RETAIN_VOICE = "1"

# Constrain CPU-heavy native math thread pools.
$env:OMP_NUM_THREADS = "4"
$env:MKL_NUM_THREADS = "4"
$env:OPENBLAS_NUM_THREADS = "4"
$env:NUMEXPR_MAX_THREADS = "4"
$env:UV_THREADPOOL_SIZE = "4"
