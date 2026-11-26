import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AutomationSmokeTests(unittest.TestCase):
    def test_page_generator_escapes_content_and_creates_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            shutil.copytree(ROOT / "page-generator", work / "page-generator")
            generator = work / "page-generator"
            item = {
                "title": "<unsafe>",
                "description": "A & B",
                "cta": "Open",
                "ctaUrl": "https://example.com/?a=1&b=2",
                "image": "img",
                "audio": "audio",
            }
            (generator / "content-library" / "smoke.json").write_text(
                json.dumps(item), encoding="utf-8"
            )
            state = {"pageCount": 0, "queue": ["smoke"], "lastUsedId": None, "lastUpdate": None}
            (generator / "build-state.json").write_text(json.dumps(state), encoding="utf-8")
            subprocess.run(["node", "build-pages.js"], cwd=generator, check=True, capture_output=True)
            html = (generator / "pages" / "page-0001.html").read_text(encoding="utf-8")
            self.assertIn("&lt;unsafe&gt;", html)
            self.assertIn("A &amp; B", html)
            self.assertIn('<a class="cta-button"', html)
            self.assertNotIn('<button class="cta-button"', html)


if __name__ == "__main__":
    unittest.main()


def test_js_repair_fixes_literal_backslash_n_between_statements():
    from md1_global_agent.publish import js_repair
    spec = {"script_js": "const a = 1;\\n  const b = () => { return a; };\\n  b();"}
    assert js_repair.check_and_repair(spec) == ""
    assert "\\n" not in spec["script_js"] and "\n  const b" in spec["script_js"]


def test_js_repair_keeps_valid_scripts_and_still_rejects_real_errors():
    from md1_global_agent.publish import js_repair
    ok = {"script_js": "const s = 'a\\nb';\nconsole.log(s);"}
    assert js_repair.check_and_repair(ok) == "" and ok["script_js"] == "const s = 'a\\nb';\nconsole.log(s);"
    assert js_repair.check_and_repair({"script_js": "const x = ;"}).startswith("js syntax error")
