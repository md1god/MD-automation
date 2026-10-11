"""Builds ONE real, working, client-side Arabic tool per run and hands it to mdm1.org as data.

Why: a plan page earns nothing; a free useful tool earns search traffic (and AdSense). The site's own
generator validates the spec again (no scripts/network/eval, Arabic, FAQ, JS syntax) and renders it with the
site template, so nothing unvetted is ever published. Source-project names never enter this flow: ideas come
from a curated evergreen list of high-demand utilities.
"""
import json
import re
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone

import requests

from builder.planner import complete
from publish.mdm1_page import API, SITE_URL, SITE_REPO, _headers, preflight

TOOL_WORKFLOW = "trend-pages.yml"

IDEAS = [
    ("hijri-gregorian-converter", "محول التاريخ الهجري والميلادي في الاتجاهين باستخدام Intl.DateTimeFormat مع التقويم islamic-umalqura"),
    ("inheritance-calculator", "حاسبة المواريث الشرعية المبسطة: زوج/زوجة، أب، أم، أبناء، بنات، مع شرح كل نصيب وتنبيه بمراجعة جهة الفتوى"),
    ("bmi-calculator", "حاسبة مؤشر كتلة الجسم والوزن المثالي والسعرات اليومية التقريبية"),
    ("end-of-service-calculator", "حاسبة مكافأة نهاية الخدمة حسب سنوات العمل والراتب الأخير (مبسّطة مع تنبيه)"),
    ("loan-installment-calculator", "حاسبة القسط الشهري للقرض والفائدة الإجمالية وجدول السداد"),
    ("age-calculator", "حاسبة العمر بالسنوات والشهور والأيام والتاريخ الهجري المقابل وموعد عيد الميلاد القادم"),
    ("discount-calculator", "حاسبة الخصم والضريبة وسعر البيع بعد الخصم ونسبة التوفير"),
    ("percentage-calculator", "حاسبة النسبة المئوية بكل صورها: كم يساوي ٪ من رقم، نسبة التغيير، الرقم الأصلي"),
    ("pregnancy-due-date-calculator", "حاسبة موعد الولادة المتوقع وعمر الحمل بالأسابيع"),
    ("missed-prayers-fasting-planner", "حاسبة قضاء الصيام والصلوات الفائتة وخطة سداد يومية"),
    ("arabic-text-counter", "عداد كلمات وحروف النص العربي ووقت القراءة وإزالة التشكيل والمسافات الزائدة"),
    ("profit-margin-calculator", "حاسبة هامش الربح وسعر البيع والتكلفة للتجار والمتاجر الإلكترونية"),
    ("gold-value-calculator", "حاسبة قيمة الذهب حسب الوزن والعيار (24/22/21/18) وسعر الجرام والمصنعية"),
    ("date-difference-calculator", "حاسبة الفرق بين تاريخين بالأيام والأسابيع والشهور وأيام العمل"),
    ("password-generator", "مولّد كلمات مرور قوية مع مقياس القوة داخل المتصفح"),
    ("split-bill-calculator", "حاسبة تقسيم الفاتورة بين الأصدقاء مع البقشيش والضريبة"),
    ("trip-fuel-cost-calculator", "حاسبة تكلفة الرحلة والبنزين حسب المسافة واستهلاك السيارة وسعر اللتر"),
    ("unit-converter-arabic", "محول وحدات عربي: الطول والوزن والحرارة والمساحة والحجم"),
    ("net-salary-calculator", "حاسبة صافي الراتب بعد الخصومات والتأمينات والضريبة بنسب يدخلها المستخدم"),
    ("study-time-planner", "مخطط مذاكرة يوزّع المواد على الأيام المتبقية للامتحان حسب الصعوبة"),
]

PROMPT = """You are building ONE original, genuinely useful, single-page Arabic web tool for a website.
Tool to build: {idea}
Rules: fully working CLIENT-SIDE tool (HTML form + vanilla JS; no server, no network, no external libs); everything written from scratch; Arabic UI text; correct logic and sensible validation of inputs.
Return ONLY JSON, no markdown fences:
{{"slug":"{slug}","title":"Arabic SEO title <=70 chars","h1":"Arabic heading","description":"Arabic meta description 110-160 chars",
"body_html":"intro paragraph (>=80 words, starts with a quick answer) + form/inputs/button/output. Every element needs an id; wrap the result in <div class=\\"out\\" id=\\"out\\" style=\\"display:none\\">; use only <p>,<b>,<label>,<input>,<select>,<option>,<textarea>,<button>,<div>,<br>,<small>; NO <script>, NO <style>, NO inline on* handlers, NO external src/href",
"script_js":"vanilla JS wiring those ids (no fetch/XMLHttpRequest/eval/URLs)","faq":[{{"q":"..","a":".."}}]}}
faq must have 3 to 5 items. At least 500 Arabic characters of visible text in body_html."""


def pick_idea(ledger):
    for slug, idea in IDEAS:
        if not ledger.is_known("tool:" + slug):
            return slug, idea
    return None


def _json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in answer")
    return json.loads(text[start:end + 1])


def check(spec: dict) -> str:
    """'' if the spec passes local checks, else the reason (also fed back to the model)."""
    for k in ("slug", "title", "h1", "description", "body_html", "script_js"):
        if not isinstance(spec.get(k), str) or not spec[k].strip():
            return f"missing {k}"
    faq = spec.get("faq")
    if not isinstance(faq, list) or not 3 <= len(faq) <= 6 or not all(isinstance(x, dict) and x.get("q") and x.get("a") for x in faq):
        return "faq must have 3-5 items with q and a"
    if len(re.sub(r"<[^>]+>", " ", spec["body_html"])) < 500 or 'id="out"' not in spec["body_html"]:
        return 'body_html too short or no id="out"'
    if re.search(r"<script|<iframe|<link|<style|\son\w+\s*=|(src|href|action)\s*=\s*[\"']?(https?:)?//", spec["body_html"], re.I):
        return "unsafe html"
    if re.search(r"fetch\s*\(|XMLHttpRequest|WebSocket|import\s*\(|eval\s*\(|new Function|document\.cookie|https?://|</script", spec["script_js"], re.I):
        return "unsafe js"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(spec["script_js"])
    res = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
    if res.returncode not in (0, 127):
        return "js syntax error: " + res.stderr[:200]
    return ""


def build(llm: dict, slug: str, idea: str, attempts: int = 3, deadline: float = None):
    """Returns (spec | None, provider, reason)."""
    feedback, provider = "", None
    for _ in range(attempts):
        prompt = PROMPT.format(idea=idea, slug=slug) + (f"\nYour previous answer was rejected: {feedback}. Fix exactly that and return the full JSON again." if feedback else "")
        try:
            spec = _json(complete(prompt, llm, deadline))
            provider = complete.used
        except Exception as exc:
            feedback = f"invalid answer ({str(exc)[:120]})"
            continue
        spec["slug"] = slug
        feedback = check(spec)
        if not feedback:
            return spec, provider, ""
    return None, provider, feedback


def publish(spec: dict, token: str, run_timeout: int = 900, live_timeout: int = 600, poll: int = 20) -> dict:
    ok, reason = preflight(token)
    if not ok:
        return {"state": "failed", "url": "", "reason": reason}
    started = datetime.now(timezone.utc) - timedelta(seconds=10)
    r = requests.post(f"{API}/repos/{SITE_REPO}/actions/workflows/{TOOL_WORKFLOW}/dispatches", headers=_headers(token),
                      json={"ref": "main", "inputs": {"tool_json": json.dumps(spec, ensure_ascii=False)}}, timeout=30)
    if r.status_code != 204:
        return {"state": "failed", "url": "", "reason": f"إرسال workflow الأدوات فشل ({r.status_code})"}
    deadline = time.time() + run_timeout
    run = None
    while time.time() < deadline:
        time.sleep(poll)
        try:
            runs = requests.get(f"{API}/repos/{SITE_REPO}/actions/workflows/{TOOL_WORKFLOW}/runs", headers=_headers(token),
                                params={"event": "workflow_dispatch", "per_page": 5}, timeout=30).json().get("workflow_runs", [])
        except (requests.RequestException, ValueError):
            continue
        fresh = [x for x in runs if datetime.fromisoformat(x["created_at"].replace("Z", "+00:00")) >= started]
        if fresh:
            run = fresh[0]
            if run["status"] == "completed":
                break
    if not run or run["status"] != "completed" or run["conclusion"] != "success":
        return {"state": "failed", "url": "", "reason": "workflow الأدوات لم ينجح"}
    url = f"{SITE_URL}/tools/{spec['slug']}.html"
    deadline = time.time() + live_timeout
    while time.time() < deadline:
        try:
            page = requests.get(url, timeout=30, headers={"Cache-Control": "no-cache"})
            if page.status_code == 200 and spec["h1"][:10] in page.text:
                return {"state": "published", "url": url, "reason": ""}
        except requests.RequestException:
            pass
        time.sleep(poll)
    return {"state": "failed", "url": "", "reason": f"الأداة أُرسلت لكنها لم تظهر على {url} (أو رُفضت في فحص الموقع)"}
