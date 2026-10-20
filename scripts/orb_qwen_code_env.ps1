$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$env:ORB_LLM_ROUTE = "local"
$env:ORB_LOCAL_LLM_BACKEND = "llamacpp"
$env:ORB_LOCAL_LLM_ENDPOINT = "http://127.0.0.1:40343"
$env:ORB_LOCAL_LLM_MODEL = "orb-local"
$env:ORB_LOCAL_LLM_SERVER = "llama.cpp"
$env:ORB_LOCAL_LLM_ACCELERATOR = "cuda"
$env:ORB_LLAMA_CPP_ROOT = "C:\Users\bryan\Downloads\llama-b10107-bin-win-cuda-13.3-x64"
$env:ORB_LLAMA_CUDA_DLL_ROOT = "C:\Users\bryan\Downloads\cudart-llama-bin-win-cuda-13.3-x64"
$env:ORB_LLAMA_CPP_SERVER_EXE = Join-Path $env:ORB_LLAMA_CPP_ROOT "llama-server.exe"
$env:ORB_LOCAL_LLM_MODEL_PATH = "C:\Users\bryan\.cache\huggingface\hub\models--Qwen--Qwen2.5-1.5B-Instruct-GGUF\snapshots\91cad51170dc346986eccefdc2dd33a9da36ead9\qwen2.5-1.5b-instruct-q4_k_m.gguf"
$env:ORB_LOCAL_LLM_HOST = "127.0.0.1"
$env:ORB_LOCAL_LLM_PORT = "40343"
$env:ORB_LOCAL_LLM_CTX_SIZE = "32768"
$env:ORB_LOCAL_LLM_GPU_LAYERS = "all"
$env:ORB_LOCAL_LLM_THREADS = "8"
$env:ORB_LOCAL_LLM_STARTUP_TIMEOUT_SEC = "120"
$env:ORB_LOCAL_LLM_LOG_DIR = Join-Path $RepoRoot ".orb-runtime\llama.cpp"

$env:ORB_QWEN_CODE_ROOT = "R:\Services\qwen-code-main\qwen-code-main"
$env:ORB_QWEN_CODE_ENTRYPOINT = Join-Path $env:ORB_QWEN_CODE_ROOT "packages\cli\dist\index.js"
$env:ORB_QWEN_CODE_COMMAND = "node"
$env:ORB_QWEN_CODE_AUTH_TYPE = "openai"
$env:ORB_QWEN_CODE_BASE_URL = "http://127.0.0.1:40343/v1"
$env:ORB_QWEN_CODE_MODEL = $env:ORB_LOCAL_LLM_MODEL
$env:ORB_QWEN_CODE_API_KEY = "local"
$env:ORB_QWEN_CODE_TIMEOUT_SEC = "90"

$env:OPENAI_BASE_URL = $env:ORB_QWEN_CODE_BASE_URL
$env:OPENAI_API_KEY = $env:ORB_QWEN_CODE_API_KEY
$env:OPENAI_MODEL = $env:ORB_QWEN_CODE_MODEL
