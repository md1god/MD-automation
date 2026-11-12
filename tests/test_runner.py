import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "md1_global_agent"))

from agents import runner  # noqa: E402


class RunnerTimeoutTests(unittest.TestCase):
    def setUp(self):
        self._orig = runner.run_cli

    def tearDown(self):
        runner.run_cli = self._orig

    def test_run_cli_kills_helpers_that_keep_the_pipe_open(self):
        # The shell starts a helper that inherits stdout and outlives it. A plain
        # subprocess.run(timeout=...) would block until the helper exits (30 s here).
        start = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            runner.run_cli(["sh", "-c", "sleep 30 & sleep 30"], 1, tempfile.gettempdir(), dict(os.environ))
        self.assertLess(time.monotonic() - start, 10)

    def test_run_agent_gives_up_when_the_time_budget_is_gone(self):
        calls = []
        runner.run_cli = lambda *a, **k: calls.append(a) or (0, "")
        with self.assertRaises(RuntimeError) as ctx:
            runner.run_agent("p", ["m1", "m2"], timeout=600, total_budget=10)
        self.assertIn("time budget", str(ctx.exception))
        self.assertEqual(calls, [])

    def test_run_agent_caps_each_attempt_by_the_remaining_budget(self):
        seen = []

        def fake(cmd, timeout, cwd, env):
            seen.append(timeout)
            return 0, 'noise <<<JSON {"items": []} JSON>>> noise'

        runner.run_cli = fake
        result, model = runner.run_agent("p", ["m1"], timeout=600, total_budget=100)
        self.assertEqual((result, model), ({"items": []}, "m1"))
        self.assertLessEqual(seen[0], 100)

    def test_run_agent_moves_on_after_a_timeout(self):
        def fake(cmd, timeout, cwd, env):
            if "opencode/slow" in cmd:
                raise subprocess.TimeoutExpired(cmd, timeout)
            return 0, '<<<JSON {"items": [1]} JSON>>>'

        runner.run_cli = fake
        result, model = runner.run_agent("p", ["slow", "fast"], timeout=600, total_budget=500)
        self.assertEqual(model, "fast")
        self.assertEqual(result, {"items": [1]})


class AgentEnvTests(unittest.TestCase):
    SECRETS = ("SITES_PAT", "BSKY_APP_PASSWORD", "MASTODON_ACCESS_TOKEN", "BOT_TOKEN",
               "TELEGRAM_BOT_TOKEN", "LEDGER_SALT", "OPENROUTER_API_KEY", "GROQ_API_KEY")

    def setUp(self):
        self._orig_run_cli = runner.run_cli
        self._saved = dict(os.environ)
        for k in self.SECRETS:
            os.environ[k] = "secret-" + k
        os.environ["OPENCODE_API_KEY"] = "model-key"

    def tearDown(self):
        runner.run_cli = self._orig_run_cli
        os.environ.clear()
        os.environ.update(self._saved)

    def test_agent_env_has_no_repo_secrets(self):
        env = runner.agent_env()
        for k in self.SECRETS:
            self.assertNotIn(k, env)
        self.assertEqual(env["OPENCODE_API_KEY"], "model-key")
        self.assertEqual(env["OPENCODE_ENABLE_EXA"], "1")
        self.assertIn('"bash": "deny"', env["OPENCODE_CONFIG_CONTENT"])

    def test_run_agent_passes_the_restricted_env_to_the_cli(self):
        seen = []
        runner.run_cli = lambda cmd, timeout, cwd, env: seen.append(env) or (0, "")
        with self.assertRaises(RuntimeError):
            runner.run_agent("p", ["m1"], timeout=60, total_budget=300)
        self.assertEqual(len(seen), 1)
        for k in self.SECRETS:
            self.assertNotIn(k, seen[0])
        self.assertNotIn("secret-SITES_PAT", " ".join(seen[0].values()))


if __name__ == "__main__":
    unittest.main()
