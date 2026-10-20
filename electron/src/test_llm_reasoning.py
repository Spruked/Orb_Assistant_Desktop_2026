"""
Tests for the reasoning-aware llama.cpp client (DeepSeek-R1-Distill-Qwen-7B).

Run from electron/src:   python -B -m unittest test_llm_reasoning -v
A stub llama.cpp server stands in for the real model; nothing here needs a GPU.
"""

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

import llm_client  # noqa: E402
from llm_client import strip_reasoning  # noqa: E402


class StubLlama:
    """Records requests and replies like llama.cpp with a DeepSeek-R1 model."""

    def __init__(self, reply="</think>\n\nThe capital of France is Paris."):
        self.requests = []
        self.reply = reply
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode())
                outer.requests.append(body)
                payload = json.dumps({"choices": [{"message": {"content": outer.reply}, "finish_reason": "stop"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                return

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class StripReasoningTests(unittest.TestCase):
    def test_complete_think_block_is_removed(self):
        self.assertEqual(strip_reasoning("<think>The user greets me.</think>\n\nHello, Bryan!"), "Hello, Bryan!")

    def test_multiline_think_block_is_removed(self):
        self.assertEqual(strip_reasoning("<think>\nline one\nline two\n</think>\nAnswer."), "Answer.")

    def test_stray_closing_tag_from_a_zero_budget_is_removed(self):
        self.assertEqual(strip_reasoning("</think>\n\nThe capital of France is Paris."), "The capital of France is Paris.")

    def test_unterminated_think_is_never_spoken(self):
        self.assertEqual(strip_reasoning("<think>I should consider whether"), "")
        self.assertEqual(strip_reasoning("Partial answer <think>and then it started thinking"), "Partial answer")

    def test_plain_text_and_empty_values_pass_through(self):
        self.assertEqual(strip_reasoning("  plain answer  "), "plain answer")
        self.assertEqual(strip_reasoning(None), "")
        self.assertEqual(strip_reasoning(""), "")

    def test_case_insensitive(self):
        self.assertEqual(strip_reasoning("<THINK>x</THINK>ok"), "ok")


class ClientRequestTests(unittest.TestCase):
    def setUp(self):
        self.stub = StubLlama()
        env = {
            "ORB_LOCAL_LLM_ENDPOINT": self.stub.url,
            "ORB_LOCAL_LLM_BACKEND": "llamacpp",
            "ORB_LOCAL_LLM_MODEL": "orb-local",
            "ORB_OLLAMA_RETRIES": "1",
            "ORB_OLLAMA_NUM_PREDICT": "256",
            "ORB_OLLAMA_TEMPERATURE": "0.6",
            "ORB_OLLAMA_STREAM": "0",
        }
        self.patch = mock.patch.dict(os.environ, env)
        self.patch.start()
        for name in ("ORB_LLM_THINKING_BUDGET", "ORB_LLM_THINKING_BUDGET_DEEP"):
            os.environ.pop(name, None)

    def tearDown(self):
        self.patch.stop()
        self.stub.close()

    def test_default_query_answers_directly_and_is_cleaned(self):
        result = llm_client.query_local_llm("What is the capital of France?")
        request = self.stub.requests[-1]
        self.assertEqual(request["thinking_budget_tokens"], 0)
        self.assertEqual(request["max_tokens"], 256)
        self.assertAlmostEqual(request["temperature"], 0.6)
        self.assertEqual(result["recommended_response"], "The capital of France is Paris.")
        self.assertEqual(result["llm_runtime"]["thinking_budget"], 0)

    def test_deep_query_gets_a_bounded_thinking_budget_on_top_of_the_answer_allowance(self):
        llm_client.query_local_llm("Plan a refactor of the ORB memory layer.", deep=True)
        request = self.stub.requests[-1]
        self.assertEqual(request["thinking_budget_tokens"], 512)
        self.assertEqual(request["max_tokens"], 256 + 512)

    def test_budgets_are_configurable_by_environment(self):
        with mock.patch.dict(os.environ, {"ORB_LLM_THINKING_BUDGET": "64", "ORB_LLM_THINKING_BUDGET_DEEP": "900"}):
            llm_client.query_local_llm("a")
            self.assertEqual(self.stub.requests[-1]["thinking_budget_tokens"], 64)
            llm_client.query_local_llm("b", deep=True)
            self.assertEqual(self.stub.requests[-1]["thinking_budget_tokens"], 900)

    def test_a_leaked_think_block_never_reaches_the_caller(self):
        self.stub.reply = "<think>Paris, obviously.</think>Paris."
        self.assertEqual(llm_client.query_local_llm("capital?")["recommended_response"], "Paris.")

    def test_llmclient_wrapper_passes_deep_through(self):
        llm_client.LLMClient().query("hard question", deep=True)
        self.assertEqual(self.stub.requests[-1]["thinking_budget_tokens"], 512)

    def test_invalid_budget_falls_back_to_the_safe_default(self):
        with mock.patch.dict(os.environ, {"ORB_LLM_THINKING_BUDGET": "not-a-number"}):
            self.assertEqual(llm_client._thinking_budget(), 0)


class ConfigTests(unittest.TestCase):
    """The launcher and instance config must offer both LLM profiles and stay launchable."""

    @classmethod
    def setUpClass(cls):
        root = SRC.parents[1]
        cls.local = (root / "orb-instance.local.ps1").read_text(encoding="utf-8")
        cls.launcher = (root / "launch_desktop_orb.ps1").read_text(encoding="utf-8")

    def profile_block(self, name):
        start = self.local.index(f'if ($env:ORB_LLM_PROFILE -eq "{name}")') if name == "deepseek7b" else self.local.index("} else {", self.local.index('ORB_LLM_PROFILE -eq "deepseek7b"'))
        end = self.local.index("} else {", start + 5) if name == "deepseek7b" else self.local.index("$env:ORB_OLLAMA_NUM_PREDICT", start)
        return self.local[start:end]

    def test_deepseek_7b_profile_is_fully_specified(self):
        block = self.profile_block("deepseek7b")
        self.assertIn("DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf", block)
        self.assertIn('ORB_LOCAL_LLM_GPU_LAYERS = "auto"', block)  # "all" would not fit 6 GB
        self.assertIn("--reasoning-format deepseek", block)
        self.assertIn("--fit on", block)
        self.assertIn('ORB_LLM_THINKING_BUDGET = "0"', block)

    def test_small_profile_keeps_the_previous_working_settings(self):
        block = self.profile_block("qwen1.5b")
        self.assertIn("qwen2.5-1.5b-instruct-q4_k_m.gguf", block)
        self.assertIn('ORB_LOCAL_LLM_GPU_LAYERS = "all"', block)
        self.assertIn('ORB_LOCAL_LLM_EXTRA_ARGS = ""', block)

    def test_both_model_files_exist(self):
        import re

        if os.name != "nt":
            self.skipTest("model paths are Windows paths")
        paths = re.findall(r'ORB_LOCAL_LLM_MODEL_PATH = "([^"]+\.gguf)"', self.local)
        self.assertEqual(len(paths), 2)
        for path in paths:
            self.assertTrue(Path(path).exists(), path)

    def test_a_default_profile_is_always_selected(self):
        self.assertRegex(self.local, r'if \(-not \$env:ORB_LLM_PROFILE\) \{ \$env:ORB_LLM_PROFILE = "(qwen1.5b|deepseek7b)" \}')

    def test_launcher_health_check_works_with_a_reasoning_model(self):
        self.assertIn("thinking_budget_tokens = 0", self.launcher)
        self.assertIn('-replace "</think>"', self.launcher)
        self.assertIn("ORB_LOCAL_LLM_EXTRA_ARGS", self.launcher)
        self.assertIn("-TimeoutSec 120", self.launcher)  # a split 7B needs a long first answer
        self.assertIn("layers were offloaded to the GPU", self.launcher)  # CPU-only fallback is announced

    def test_launcher_only_treats_a_listening_socket_as_a_taken_port(self):
        self.assertIn("-LocalPort ([int]$port) -State Listen", self.launcher)

    def test_http_timeout_leaves_room_for_a_slow_local_model(self):
        import re

        timeout = int(re.search(r'ORB_OLLAMA_TIMEOUT_SEC = "(\d+)"', self.local).group(1))
        self.assertGreaterEqual(timeout, 90)


if __name__ == "__main__":
    unittest.main()
