"""Regression tests for the failures seen in the daily Scout report:
- apps lost to "no LLM provider succeeded -> deadline reached" (a slow model ate the whole budget)
- plans rejected as too short and never retried
- "انتهت مهلة انتظار workflow موقع mdm1.org" (queued run abandoned, page possibly created anyway)
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

AGENT = Path(__file__).resolve().parents[1] / "md1_global_agent"
sys.path.insert(0, str(AGENT))

from builder import planner                                    # noqa: E402
from memory.ledger import Ledger                               # noqa: E402
from publish import app_page, mdm1_page, tool_page            # noqa: E402

os.environ["STATS_FORCE"] = "0"

REPO = {"full_name": "acme-labs/super-tracker", "url": "https://github.com/acme-labs/super-tracker",
        "category": "productivity", "description": "d", "stars": 500}
LONG_PLAN = ("1) الجمهور المستهدف\nالمستقلون الذين يحتاجون تتبع الوقت وإصدار فواتير بسهولة. " * 40 +
             "\n7) الاسم المقترح والجملة التسويقية\nالاسم المقترح: ساعاتي\nالجملة التسويقية: خطط يومك وحوّل ساعاتك إلى فاتورة\n")
SHORT_PLAN = "الاسم المقترح: ساعاتي\nالجملة التسويقية: خطط يومك\n" + "نص عربي قصير عن الفكرة. " * 15


class PlannerHealthTests(unittest.TestCase):
    LLM = {"providers": ["opencode_cli"], "models": {"opencode_cli": ["bad", "good"]}}

    def setUp(self):
        planner.reset_health()
        self._orig = planner._call_cli

    def tearDown(self):
        planner._call_cli = self._orig
        planner.reset_health()

    def test_dead_model_is_benched_after_repeated_failures(self):
        calls = []

        def fake(model, prompt, timeout=240):
            calls.append(model)
            if model == "bad":
                raise RuntimeError("cli timeout after 240s")
            return "ok"

        planner._call_cli = fake
        for _ in range(4):
            self.assertEqual(planner.complete("p", self.LLM), "ok")
        self.assertEqual(calls.count("bad"), planner.MAX_FAILS)       # not retried (and not waited on) forever
        self.assertEqual(planner.complete.used, "opencode_cli/good")

    def test_outage_raises_llm_unavailable_which_is_still_a_runtime_error(self):
        def fake(model, prompt, timeout=240):
            raise RuntimeError("boom")

        planner._call_cli = fake
        with self.assertRaises(planner.LLMUnavailable) as ctx:
            planner.complete("p", self.LLM)
        self.assertIsInstance(ctx.exception, RuntimeError)
        self.assertTrue(str(ctx.exception).startswith("no LLM provider succeeded"))

    def test_expired_deadline_is_an_outage_not_a_crash(self):
        planner._call_cli = lambda *a, **k: "never"
        with self.assertRaises(planner.LLMUnavailable) as ctx:
            planner.complete("p", self.LLM, deadline=time.time() - 1)
        self.assertIn("deadline reached", str(ctx.exception))

    def test_call_timeout_never_exceeds_remaining_budget(self):
        seen = []

        def fake(model, prompt, timeout=240):
            seen.append(timeout)
            return "ok"

        planner._call_cli = fake
        planner.complete("p", self.LLM, deadline=time.time() + 40)
        self.assertTrue(15 <= seen[0] <= 40, seen)
        planner.complete("p", self.LLM)                                # no deadline -> default
        self.assertEqual(seen[1], 240)

    def test_cli_timeout_message_does_not_contain_the_prompt(self):
        orig_run, orig_which = subprocess.run, planner.shutil.which

        def boom(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))

        subprocess.run, planner.shutil.which = boom, lambda n: "/usr/bin/opencode"
        try:
            with self.assertRaises(RuntimeError) as ctx:
                planner._call_cli("m", "SECRET-SOURCE-NAME", 5)
        finally:
            subprocess.run, planner.shutil.which = orig_run, orig_which
        self.assertNotIn("SECRET", str(ctx.exception))
        self.assertIn("timeout", str(ctx.exception))


class BuilderOutageTests(unittest.TestCase):
    def test_app_build_reports_outage_when_nothing_ever_answered(self):
        orig = app_page.complete

        def down(*a, **k):
            raise planner.LLMUnavailable("no LLM provider succeeded -> deadline reached")

        app_page.complete = down
        try:
            spec, _prov, why = app_page.build({}, "slug-x", "idea")
        finally:
            app_page.complete = orig
        self.assertIsNone(spec)
        self.assertTrue(why.startswith(planner.LLM_DOWN))

    def test_app_build_keeps_the_content_problem_when_time_runs_out_later(self):
        orig = app_page.complete
        calls = {"n": 0}

        def flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                return "TITLE: x\nH1: y\n===BODY===\n<p>قصير</p>\n===JS===\nvar a=1;\n"
            raise planner.LLMUnavailable("no LLM provider succeeded -> deadline reached")

        flaky.used = "m"
        app_page.complete = flaky
        try:
            spec, _prov, why = app_page.build({}, "slug-x", "idea")
        finally:
            app_page.complete = orig
        self.assertIsNone(spec)
        self.assertFalse(why.startswith(planner.LLM_DOWN))           # a real rejection reason survives
        self.assertIn("time budget used up", why)

    def test_tool_build_stops_retrying_during_an_outage(self):
        orig, calls = tool_page.complete, []

        def down(*a, **k):
            calls.append(1)
            raise planner.LLMUnavailable("no LLM provider succeeded -> x")

        tool_page.complete = down
        try:
            spec, _prov, why = tool_page.build({}, "age-calculator", "idea")
        finally:
            tool_page.complete = orig
        self.assertIsNone(spec)
        self.assertEqual(len(calls), 1)
        self.assertTrue(why.startswith(planner.LLM_DOWN))

    def test_idea_from_opportunity_propagates_outage(self):
        orig = app_page.complete

        def down(*a, **k):
            raise planner.LLMUnavailable("x")

        app_page.complete = down
        opp = {"repo": dict(REPO)}
        try:
            with self.assertRaises(planner.LLMUnavailable):
                app_page.idea_from_opportunity({}, opp, [])
        finally:
            app_page.complete = orig

    def test_outage_does_not_mark_ideas_failed_and_stops_the_app_phase(self):
        import main
        ledger = Ledger(Path(tempfile.mkdtemp()) / "l.json")
        orig = main.app_page.build
        main.app_page.build = lambda *a, **k: (None, None, planner.LLM_DOWN + "x")
        try:
            out = main.build_apps({"publish_apps": True, "apps_per_run": 3, "llm": {}}, ledger, [])
        finally:
            main.app_page.build = orig
        first = app_page.IDEAS[0][0]
        self.assertFalse(ledger.is_known("app:" + first))             # retried next run, not burned
        self.assertEqual(out.count("لم يُبنَ"), 1)                    # and the phase stopped at the first one


class PlanRewriteTests(unittest.TestCase):
    def setUp(self):
        import main
        self.main = main
        self.orig = (main.make_plan, planner.expand_plan, main.telegram.send_private)
        main.make_plan = lambda o, llm=None: SHORT_PLAN
        main.make_plan.used = "m"
        main.telegram.send_private = lambda t: True
        self.best = {"repo": dict(REPO), "analysis": {"score": 99.0}, "mode": "rebuild_original", "builder": {}}
        self.cfg = {"llm": {}, "publish_pages": False}
        self.ledger = Ledger(Path(tempfile.mkdtemp()) / "l.json")

    def tearDown(self):
        self.main.make_plan, planner.expand_plan, self.main.telegram.send_private = self.orig

    def test_short_plan_is_rewritten_once_and_then_passes_the_gate(self):
        seen = []

        def expand(plan, problem, llm=None, deadline=None):
            seen.append(problem)
            return LONG_PLAN

        planner.expand_plan = expand
        err, outcome, _prov, payload, _sent = self.main.plan_and_publish(self.best, self.cfg, self.ledger)
        self.assertIsNone(err)
        self.assertEqual(outcome["state"], "held")                    # got past the gate (publishing is paused)
        self.assertEqual(len(seen), 1)
        self.assertIn("قصير", seen[0])
        self.assertGreaterEqual(len(payload["body"]), mdm1_page.MIN_BODY)

    def test_rewrite_attempts_are_capped(self):
        calls = []

        def expand(plan, problem, llm=None, deadline=None):
            calls.append(1)
            return SHORT_PLAN

        planner.expand_plan = expand
        err, outcome, *_ = self.main.plan_and_publish(self.best, self.cfg, self.ledger)
        self.assertEqual(len(calls), self.main.MAX_PLAN_FIXES)
        self.assertEqual(outcome["state"], "failed")
        self.assertIn("قصير", outcome["reason"])

    def test_uncurable_rejection_is_not_rewritten(self):
        self.main.make_plan = lambda o, llm=None: "plain english only " * 300 + "\nالاسم المقترح: س\n"
        self.main.make_plan.used = "m"
        calls = []
        planner.expand_plan = lambda *a, **k: calls.append(1) or LONG_PLAN
        _err, outcome, *_ = self.main.plan_and_publish(self.best, self.cfg, self.ledger)
        self.assertEqual(outcome["state"], "failed")
        self.assertEqual(calls, [])

    def test_failed_rewrite_call_falls_back_to_the_rejection(self):
        def down(*a, **k):
            raise planner.LLMUnavailable("no LLM provider succeeded -> x")

        planner.expand_plan = down
        err, outcome, *_ = self.main.plan_and_publish(self.best, self.cfg, self.ledger)
        self.assertIsNone(err)
        self.assertEqual(outcome["state"], "failed")


# ---------------------------------------------------------------- site publishing (fake GitHub + clock)

class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def time(self):
        return self.now

    def sleep(self, s):
        self.now += s


def _resp(status, data):
    return SimpleNamespace(status_code=status, ok=status < 400, text=json.dumps(data), json=lambda: data)


class FakeSite:
    """script(i, age) -> None (no run yet) or (status, conclusion) for the i-th dispatch, `age` seconds after it."""

    def __init__(self, clock, script, registry=None, page_live=True):
        self.clock, self.script, self.registry = clock, script, list(registry or [])
        self.page_live, self.dispatch_times, self.payload = page_live, [], None

    @property
    def dispatches(self):
        return len(self.dispatch_times)

    def post(self, url, headers=None, json=None, timeout=None):
        self.dispatch_times.append(self.clock.now)
        self.payload = json["inputs"]
        return _resp(204, {})

    def get(self, url, params=None, headers=None, timeout=None):
        if url.endswith("/repos/md1god/mdm1.org"):
            return _resp(200, {})
        if url.endswith("pages-registry.json"):
            return _resp(200, self.registry)
        if "/runs" in url:
            runs = []
            for i, t in enumerate(self.dispatch_times):
                state = self.script(i, self.clock.now - t)
                if state is None:
                    continue
                status, conclusion = state
                if status == "completed" and conclusion == "success" and not any(
                        e["scoutId"] == self.payload["scout_id"] for e in self.registry):
                    self.registry.append({"scoutId": self.payload["scout_id"], "slug": "678"})
                runs.append({"status": status, "conclusion": conclusion,
                             "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})
            return _resp(200, {"workflow_runs": list(reversed(runs))})
        if "/pages/" in url:
            text = mdm1_page._js_escape(PublishTests.PAYLOAD["title"]) if self.page_live else "not yet"
            return SimpleNamespace(status_code=200 if self.page_live else 404, text=text)
        raise AssertionError("unexpected GET " + url)


class PublishTests(unittest.TestCase):
    PAYLOAD = {"id": "p1", "title": "ساعاتي — خطة مشروع كاملة", "description": "d", "body": "b", "translations": {}}

    def _publish(self, script, registry=None, page_live=True, **kw):
        clock = Clock()
        site = FakeSite(clock, script, registry, page_live)
        orig = (mdm1_page.requests, mdm1_page.time)
        mdm1_page.requests = SimpleNamespace(get=site.get, post=site.post,
                                             RequestException=orig[0].RequestException)
        mdm1_page.time = clock
        try:
            out = mdm1_page.publish(dict(self.PAYLOAD), "tok", **kw)
        finally:
            mdm1_page.requests, mdm1_page.time = orig
        return out, site, clock

    def test_already_on_the_site_is_verified_without_a_second_dispatch(self):
        out, site, _ = self._publish(lambda i, age: None, registry=[{"scoutId": "p1", "slug": "678"}])
        self.assertEqual(out["state"], "published")
        self.assertEqual(out["url"], "https://mdm1.org/pages/678.html")
        self.assertEqual(site.dispatches, 0)

    def test_slow_queue_beyond_the_normal_timeout_is_waited_out(self):
        # queued for 700 s (> run_timeout 600) behind deploy.yml in the shared "pages" group, then succeeds
        script = lambda i, age: ("queued", None) if age < 700 else ("completed", "success")
        out, site, clock = self._publish(script)
        self.assertEqual(out["state"], "published")
        self.assertEqual(site.dispatches, 1)
        self.assertGreater(clock.now - site.dispatch_times[0], 600)

    def test_dispatch_that_never_starts_is_retried_once(self):
        out, site, _ = self._publish(lambda i, age: None)
        self.assertEqual(out["state"], "failed")
        self.assertIn("لم يبدأ", out["reason"])
        self.assertEqual(site.dispatches, 2)

    def test_cancelled_run_is_redispatched(self):
        # the first run is replaced in the concurrency queue; the second one goes through
        script = lambda i, age: ("completed", "cancelled") if i == 0 else ("completed", "success")
        out, site, _ = self._publish(script)
        self.assertEqual(out["state"], "published")
        self.assertEqual(site.dispatches, 2)

    def test_run_stuck_forever_reports_timeout_after_the_grace_period(self):
        out, site, clock = self._publish(lambda i, age: ("in_progress", None))
        self.assertEqual(out["state"], "failed")
        self.assertIn("انتهت مهلة انتظار workflow موقع mdm1.org", out["reason"])
        self.assertEqual(site.dispatches, 1)
        self.assertLess(clock.now - site.dispatch_times[0], 600 + 600 + 60)

    def test_failed_run_whose_page_was_committed_still_counts_as_published(self):
        # deploy step failed after the commit: the registry (source of truth) has the page and it is live later
        site_registry = []
        script = lambda i, age: ("completed", "failure")
        out, site, _ = self._publish(script, registry=site_registry)
        self.assertEqual(out["state"], "failed")                       # nothing committed -> honest failure
        self.assertIn("failure", out["reason"])
        site_registry.append({"scoutId": "p1", "slug": "678"})
        out2, site2, _ = self._publish(script, registry=site_registry)
        self.assertEqual(out2["state"], "published")
        self.assertEqual(site2.dispatches, 0)

    def test_missing_token_still_fails_loudly(self):
        self.assertEqual(mdm1_page.publish(dict(self.PAYLOAD), "")["state"], "failed")


class ToolIdeaTests(unittest.TestCase):
    def test_ideas_are_unique_kebab_case_and_plentiful(self):
        slugs = [s for s, _ in tool_page.IDEAS]
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertTrue(all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s) for s in slugs))
        self.assertTrue(all(re.search(r"[؀-ۿ]", t) for _, t in tool_page.IDEAS))
        self.assertGreaterEqual(len(slugs), 40)


if __name__ == "__main__":
    unittest.main()
