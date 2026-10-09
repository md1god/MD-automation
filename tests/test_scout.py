import os
import sys
import tempfile
import unittest
from pathlib import Path

AGENT = Path(__file__).resolve().parents[1] / "md1_global_agent"
sys.path.insert(0, str(AGENT))

from memory.ledger import Ledger, key_for, public_id          # noqa: E402
import privacy                                                 # noqa: E402
from publish import mdm1_page, translate                      # noqa: E402
from notify import telegram                                    # noqa: E402
from agent import _unique_new                                  # noqa: E402

REPO = {"full_name": "acme-labs/super-tracker", "url": "https://github.com/acme-labs/super-tracker",
        "category": "productivity", "description": "d", "stars": 500}
PLAN = ("1) الجمهور المستهدف\nالمستقلون الذين يحتاجون تتبع الوقت وإصدار فواتير بسهولة. " * 6 +
        "\n7) الاسم المقترح والجملة التسويقية\nالاسم المقترح: ساعاتي\nالجملة التسويقية: خطط يومك وحوّل ساعاتك إلى فاتورة\n"
        "هذا الملف مبني على super-tracker من acme-labs https://github.com/acme-labs/super-tracker")


class LedgerTests(unittest.TestCase):
    def test_two_levels_and_no_names_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            lg = Ledger(path)
            self.assertFalse(lg.is_known("Foo/Bar"))
            lg.mark_examined("Foo/Bar")
            lg.mark_published("Other/Thing", "https://mdm1.org/pages/1.html")
            lg.save()
            again = Ledger(path)
            self.assertTrue(again.is_examined("foo/bar"))        # case-insensitive
            self.assertTrue(again.is_published("Other/Thing"))
            self.assertTrue(again.is_known("Other/Thing"))
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("Foo", raw)
            self.assertNotIn("Bar", raw)
            self.assertNotIn("Thing", raw)

    def test_unique_new_filters_known_and_duplicates(self):
        lg = Ledger(Path(tempfile.mkdtemp()) / "l.json")
        lg.mark_examined("seen/one")
        repos = [{"full_name": "seen/one"}, {"full_name": "new/two"}, {"full_name": "NEW/two"}]
        self.assertEqual([r["full_name"] for r in _unique_new(repos, lg)], ["new/two"])

    def test_legacy_import(self):
        lg = Ledger(Path(tempfile.mkdtemp()) / "l.json")
        self.assertEqual(lg.import_legacy_names(["a/b", "c/d"]), 2)
        self.assertTrue(lg.is_known("A/B"))


class PrivacyAndPayloadTests(unittest.TestCase):
    def test_source_identity_is_removed_and_page_passes_gate(self):
        terms = privacy.identity_terms(REPO)
        payload = mdm1_page.build_payload(PLAN, public_id(REPO["full_name"]), terms, key_for(REPO["full_name"]))
        whole = payload["title"] + payload["description"] + payload["body"]
        self.assertEqual(privacy.leaks(whole, terms), [])
        self.assertIn("ساعاتي", payload["title"])

    def test_gate_rejects_leak_short_and_non_arabic(self):
        terms = privacy.identity_terms(REPO)
        ok = mdm1_page.build_payload(PLAN, "abc", terms)
        bad = dict(ok, body=ok["body"] + " super-tracker")
        self.assertFalse(mdm1_page.quality_gate(bad, terms)[0])
        self.assertFalse(mdm1_page.quality_gate(dict(ok, body="قصير"), terms)[0])
        self.assertFalse(mdm1_page.quality_gate(dict(ok, title="English", description="English only", body="x " * 600), terms)[0])
        with self.assertRaises(mdm1_page.PageRejected):
            mdm1_page.build_payload("قصير", "abc", terms)

    def test_telegram_report_has_no_source_names_and_reports_publish(self):
        opp = [{"repo": REPO, "analysis": {"score": 90}, "mode": "rebuild_original"}]
        text = telegram.daily_report({"dry_run": False}, opp, {"total": 5}, "abc", "opencode_cli/x", None,
                                     {"state": "published", "url": "https://mdm1.org/pages/90.html", "reason": ""},
                                     {"title": "ساعاتي", "languages": ["ar", "en", "es"]}, True)
        self.assertNotIn("super-tracker", text)
        self.assertNotIn("acme-labs", text)
        self.assertIn("تم النشر فعليًا", text)
        self.assertIn("https://mdm1.org/pages/90.html", text)
        failed = telegram.daily_report({"dry_run": False}, opp, {"total": 5}, "abc", "m", None,
                                       {"state": "failed", "url": "", "reason": "SITES_PAT منتهي"}, None, False)
        self.assertIn("النشر لم يتم", failed)
        self.assertNotIn("تم النشر فعليًا", failed)

    def test_promo_is_bilingual_and_has_link(self):
        payload = {"title": "ساعاتي — خطة", "description": "وصف", "translations": {"en": {"title": "Hours", "description": "Plan"}}}
        text = telegram.promo_text(payload, "https://mdm1.org/pages/90.html", ["ar", "en"])
        self.assertIn("Hours", text)
        self.assertIn("https://mdm1.org/pages/90.html", text)


class TranslateTests(unittest.TestCase):
    ANSWER = "TITLE: Hours — project under study\nDESCRIPTION: Plan your day\nBODY:\n" + "Freelancers need simple time tracking. " * 20

    def test_parse_and_gate(self):
        terms = privacy.identity_terms(REPO)
        item = translate.parse(self.ANSWER)
        self.assertIsNotNone(item)
        self.assertTrue(translate.gate(item, "س" * 1000, terms)[0])
        leaked = dict(item, body=item["body"] + " built on super-tracker")
        self.assertFalse(translate.gate(leaked, "س" * 1000, terms)[0])
        arabic = dict(item, body="هذا نص عربي لم يترجم " * 40)
        self.assertFalse(translate.gate(arabic, "س" * 1000, terms)[0])
        self.assertIsNone(translate.parse("no markers here"))

    def test_translate_all_skips_failures(self):
        calls = []

        def fake(prompt, llm=None, deadline=None):
            calls.append(prompt)
            if "French" in prompt:
                raise RuntimeError("model down")
            return self.ANSWER
        original = translate.complete
        translate.complete = fake
        try:
            payload = {"title": "ساعاتي", "description": "وصف", "body": "نص عربي طويل " * 100}
            out = translate.translate_all(payload, privacy.identity_terms(REPO), {}, ["en", "fr", "de"], budget=60)
        finally:
            translate.complete = original
        self.assertEqual(sorted(out), ["de", "en"])


if __name__ == "__main__":
    unittest.main()
