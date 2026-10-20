# Local LLM runtime - llama.cpp + DeepSeek-R1-Distill-Qwen-7B

The ORB's conversation model is **DeepSeek-R1-Distill-Qwen-7B (Q4_K_M)**, a Qwen2.5-7B based DeepSeek reasoning distill, served by
**llama.cpp** (build b10107, CUDA 13.3) on `127.0.0.1:40343`. It replaced Qwen2.5-1.5B-Instruct on 2026-10-20. The server alias stays
`orb-local`, so nothing else in the ORB needs to know which model is loaded.

Model file: `C:\Users\bryan\.cache\huggingface\hub\models--bartowski--DeepSeek-R1-Distill-Qwen-7B-GGUF\snapshots\361004151d4f4f6b446dc5e6d46fbf4422a80d5f\DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf` (4.36 GB).

## Configuration (`orb-instance.local.ps1`, started by `launch_desktop_orb.ps1`)

| Setting | Value | Why |
|---|---|---|
| `ORB_LOCAL_LLM_MODEL_PATH` | the file above | selects the model |
| `ORB_LOCAL_LLM_CTX_SIZE` | 8192 | the old 32768 context does not fit with a 7B model |
| `ORB_LOCAL_LLM_GPU_LAYERS` | `auto` | `all` cannot fit 6 GB; llama.cpp splits layers across GPU and CPU |
| `ORB_LOCAL_LLM_THREADS` | 4 | the CPU (i5-3470) has 4 cores |
| `ORB_LOCAL_LLM_EXTRA_ARGS` | `--fit on --fit-target 768 --parallel 1 --jinja --reasoning-format deepseek --reasoning-budget 384 --temp 0.6 --top-p 0.95` | fit to free VRAM with a 768 MiB margin, one slot, reasoning returned separately from the answer, DeepSeek's recommended sampling |
| `ORB_LLM_THINKING_BUDGET` | 0 | answer directly (fast) for normal conversation |
| `ORB_LLM_THINKING_BUDGET_DEEP` | 512 | bounded thinking for questions worth the wait |
| `ORB_OLLAMA_TIMEOUT_SEC` / `_TEMPERATURE` / `_NUM_PREDICT` | 120 / 0.6 / 256 | a slow local model needs a longer timeout; 0.6 is DeepSeek's recommended temperature |

The launcher gained `ORB_LOCAL_LLM_EXTRA_ARGS`, and its health check now works with a reasoning model: it asks for a direct answer
(`thinking_budget_tokens = 0`) and ignores a stray `</think>`.

## What the ORB does with a reasoning model

* **Per-request thinking budget.** `llm_client.query_local_llm(text, deep=False)` sends `thinking_budget_tokens` (0 by default, 512 with `deep=True`) and
  adds the budget to `max_tokens` so thinking never eats the answer allowance. `LLMClient.query(text, deep=...)` passes it through.
  No caller uses `deep=True` yet; wiring it to a route (for example governance deep reasoning) is open.
* **Reasoning is never spoken or shown.** `strip_reasoning()` removes a complete `<think>` block, a stray leading `</think>` (left when thinking is
  skipped) and an unterminated `<think>`. The MCP's `orb_llm/local_llm.py` does the same.
* Tests: `electron/src/test_llm_reasoning.py` (16, against a stub llama.cpp server).

## Measured on this machine (RTX 3050 6 GB, i5-3470, 7 GB free RAM)

* Server footprint about 2.4 GB of VRAM with the automatic fit; the Windows compositor and other apps already hold about 3.2 GB, so a full offload is impossible.
* Generation about 8 to 9 tokens per second (hybrid GPU/CPU; the CPU has no AVX2).
* "What is the capital of France?": about 1.6 s with `thinking_budget_tokens: 0` (13 tokens), about 20 s with the default thinking (about 150 reasoning tokens first).
* The server-wide `--reasoning-budget` flag did not change latency when tried per request; the per-request field `thinking_budget_tokens` did.

## Caveats

* The model reasons at length by default; keep the default budget at 0 for voice, and use the deep budget deliberately.
* `llm_client` retries 3 times; with a 120 s timeout a dead server can hold a query for several minutes before the governed fallback runs.
* A second llama-server (pid 6716, another account) was running during setup and could not be stopped; it is not this ORB's.
* The Epistemic Gravity Field (now enabled, about 80 ms per cursor sample on CPU) competes with the model for the same 4 CPU cores.

## Profiles (added 2026-10-20, later in the session)

The 7B model and the Qwen3-TTS voice bridge (about 3.9 GB of VRAM) cannot share the 6 GB GPU, and the 7B model ran partly on the CPU.
`orb-instance.local.ps1` therefore holds two profiles, chosen with `ORB_LLM_PROFILE`:

| Profile | Model | Use |
| --- | --- | --- |
| `qwen1.5b` (default) | Qwen2.5-1.5B-Instruct, ctx 32768, all layers on GPU, 8 threads | works alongside the voice stack |
| `deepseek7b` | DeepSeek-R1-Distill-Qwen-7B Q4_K_M, ctx 8192, `--gpu-layers auto`, 4 threads, budgets 0/512 | the requested model; use when voice is not running |

Launcher fixes made on the way: the chat health timeout is now 120 s (a cold 7B load is slow), and the "port occupied" check
looks only at `Listen` sockets (a TIME_WAIT socket was blocking startup). Voice is deferred to the other machine.
