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


if __name__ == "__main__":
    unittest.main()
