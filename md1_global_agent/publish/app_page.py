"""Builds ONE complete, working, client-side Arabic web APP per run and hands it to mdm1.org/apps.

Ideas = the FUNCTION of products people search for every day (closed-source or open-source alike). Only the
idea is taken: code, design, names and branding are written from scratch, so nothing is copied.
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

APP_WORKFLOW = "add-app.yml"
MAX_HTML = 60000

IDEAS = [
    ("photo-editor-online", "محرر صور على المتصفح: رفع صورة، قص، تدوير، سطوع وتباين وتشبع، فلاتر (أبيض وأسود، سيبيا)، رسم وكتابة نص، تراجع وإعادة، وتنزيل PNG/JPG — باستخدام canvas فقط"),
    ("image-compressor-resizer", "ضغط وتصغير الصور داخل المتصفح: رفع صور متعددة، اختيار الجودة والأبعاد، معاينة الحجم قبل وبعد، تنزيل النتيجة"),
    ("kanban-task-board", "لوحة مهام كانبان بثلاثة أعمدة قابلة للتعديل، سحب وإفلات البطاقات، ألوان وتواريخ استحقاق، حفظ في localStorage وتصدير/استيراد JSON"),
    ("invoice-generator", "منشئ فواتير احترافي: بيانات البائع والعميل، بنود وضريبة وخصم، حساب تلقائي، معاينة وطباعة PDF من المتصفح، حفظ المسودات"),
    ("resume-builder-arabic", "منشئ سيرة ذاتية عربية: نماذج لإدخال الخبرات والتعليم والمهارات، 3 قوالب، معاينة حية وطباعة PDF"),
    ("markdown-notes-editor", "محرر ملاحظات بتنسيق Markdown مع معاينة حية، مجلدات وبحث، حفظ تلقائي في localStorage وتنزيل الملفات"),
    ("whiteboard-drawing", "سبورة رسم: فرشاة وممحاة وأشكال وألوان وسُمك، تراجع وإعادة، لوحة لا نهائية بالتحريك، حفظ كصورة"),
    ("habit-and-pomodoro-tracker", "متتبع عادات يومية مع شبكة تقدم أسبوعية وشهرية وسلاسل الإنجاز، ومؤقت بومودورو مدمج وإحصاءات"),
    ("meme-poster-maker", "صانع ميمز وبوسترات: رفع صورة أو خلفية لونية، نصوص متعددة بخطوط وألوان وحدود، سحب النصوص، وتنزيل الصورة"),
    ("spreadsheet-lite", "جدول بيانات خفيف: شبكة خلايا قابلة للتحرير، صيغ SUM/AVERAGE/MIN/MAX/IF والعمليات الأساسية، تنسيق، تصدير CSV واستيراده"),
    ("json-regex-dev-toolbox", "صندوق أدوات المطور: منسّق JSON ومدقق، مختبر Regex مع إبراز التطابق، محول Base64 وURL، مقارنة نصين"),
    ("flashcards-spaced-repetition", "بطاقات تعليمية بالتكرار المتباعد: إنشاء مجموعات، مراجعة يومية بخوارزمية SM-2 مبسطة، إحصاءات، استيراد وتصدير"),
]

PROMPT = """You are an expert front-end engineer. Build ONE complete, polished, genuinely useful Arabic (RTL) web app as a SINGLE self-contained HTML file.
App: {idea}
Hard rules:
- One file: <!DOCTYPE html>, <html lang="ar" dir="rtl">, a <title>, inline <style> and ONE inline <script>. No external files, fonts, images, CDNs or URLs of any kind (no "http"), no iframes.
- No network (no fetch/XMLHttpRequest/WebSocket), no eval/new Function, no document.cookie, no window.open. localStorage inside try/catch is fine.
- Responsive and touch friendly, dark elegant design, clear Arabic UI, empty/error states, keyboard shortcuts where natural.
- Every feature listed above must really work. Write it from scratch; do not imitate any product's branding or name.
- Maximum 45000 characters in total.
- Include <title> (Arabic SEO title, at most 70 characters) and <meta name="description" content="..."> (Arabic, 110-160 characters).
Return ONLY the raw HTML file, starting with <!DOCTYPE html> and ending with </html>. No JSON, no markdown fences, no explanation."""


def pick_idea(ledger):
    for slug, idea in IDEAS:
        if not ledger.is_known("app:" + slug):
            return slug, idea
    return None


def _extract(text: str, slug: str) -> dict:
    """Raw HTML answer -> spec. Raw HTML is far more reliable than a 40k-char JSON string."""
    text = re.sub(r"^```(?:html)?\s*|\s*```$", "", (text or "").strip(), flags=re.M).strip()
    start = text.lower().find("<!doctype")
    if start < 0:
        start = text.lower().find("<html")
    end = text.lower().rfind("</html>")
    if start < 0 or end < start:
        raise ValueError("no complete HTML document in answer")
    html = text[start:end + len("</html>")]
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    desc = re.search(r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"']([^\"']*)", html, re.I)
    return {"slug": slug, "title": (title.group(1).strip() if title else "")[:90],
            "description": (desc.group(1).strip() if desc else "")[:200], "html": html}


def check(spec: dict) -> str:
    for k in ("slug", "title", "description", "html"):
        if not isinstance(spec.get(k), str) or not spec[k].strip():
            return f"missing {k}"
    h = spec["html"]
    if not 3000 <= len(h) <= MAX_HTML:
        return f"html size {len(h)} out of range 3000-{MAX_HTML}"
    if not re.search(r"<html|<body", h, re.I) or not re.search(r"[؀-ۿ]", h):
        return "not a full Arabic page"
    if re.search(r"(src|href|action|data|poster)\s*=\s*[\"']?\s*(https?:)?//|url\(\s*[\"']?\s*(https?:)?//|@import|<iframe|<object|<embed|<link", h, re.I):
        return "external resource"
    if re.search(r"fetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon|importScripts|import\s*\(|eval\s*\(|new Function|document\.cookie|window\.open|location\s*=|https?://", h, re.I):
        return "unsafe js/network or a URL in the text"
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", h, re.S | re.I)
    if not scripts or re.search(r"<script[^>]+src", h, re.I):
        return "needs inline script only"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write("\n;\n".join(scripts))
    res = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
    if res.returncode not in (0, 127):
        return "js syntax error: " + res.stderr[:200]
    return ""


def build(llm: dict, slug: str, idea: str, attempts: int = 3, deadline: float = None):
    feedback, provider = "", None
    for _ in range(attempts):
        prompt = PROMPT.format(idea=idea, slug=slug) + (f"\nYour previous answer was rejected: {feedback}. Fix exactly that and return the full JSON again." if feedback else "")
        try:
            spec = _extract(complete(prompt, llm, deadline), slug)
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
    payload = {"slug": spec["slug"], "title": spec["title"], "description": spec["description"], "html": spec["html"]}
    r = requests.post(f"{API}/repos/{SITE_REPO}/actions/workflows/{APP_WORKFLOW}/dispatches", headers=_headers(token),
                      json={"ref": "main", "inputs": {"app_json": json.dumps(payload, ensure_ascii=False)}}, timeout=30)
    if r.status_code != 204:
        return {"state": "failed", "url": "", "reason": f"إرسال workflow التطبيقات فشل ({r.status_code}: {r.text[:100]})"}
    deadline = time.time() + run_timeout
    run = None
    while time.time() < deadline:
        time.sleep(poll)
        try:
            runs = requests.get(f"{API}/repos/{SITE_REPO}/actions/workflows/{APP_WORKFLOW}/runs", headers=_headers(token),
                                params={"event": "workflow_dispatch", "per_page": 5}, timeout=30).json().get("workflow_runs", [])
        except (requests.RequestException, ValueError):
            continue
        fresh = [x for x in runs if datetime.fromisoformat(x["created_at"].replace("Z", "+00:00")) >= started]
        if fresh:
            run = fresh[0]
            if run["status"] == "completed":
                break
    if not run or run["status"] != "completed" or run["conclusion"] != "success":
        return {"state": "failed", "url": "", "reason": "workflow التطبيقات لم ينجح (رُفض التطبيق في فحص الموقع غالبًا)"}
    url = f"{SITE_URL}/apps/{spec['slug']}/"
    deadline = time.time() + live_timeout
    while time.time() < deadline:
        try:
            page = requests.get(url, timeout=30, headers={"Cache-Control": "no-cache"})
            if page.status_code == 200 and len(page.text) > 3000:
                return {"state": "published", "url": url, "reason": ""}
        except requests.RequestException:
            pass
        time.sleep(poll)
    return {"state": "failed", "url": "", "reason": f"التطبيق أُرسل لكنه لم يظهر على {url}"}
