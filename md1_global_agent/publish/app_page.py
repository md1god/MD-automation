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

import privacy
from builder.planner import complete
from publish.mdm1_page import API, SITE_URL, SITE_REPO, _headers, preflight

APP_WORKFLOW = "add-app.yml"

IDEAS = [
    ("image-format-converter", "محول صيغ الصور: رفع صورة أو عدة صور، اختيار الصيغة الناتجة (PNG وJPG وWebP) وجودة الضغط، معاينة الحجم قبل وبعد، تنزيل كل صورة أو الكل، بدون رفع أي شيء لخادم"),
    ("photo-editor-pro", "محرر صور: رفع صورة، قص بنسب جاهزة، تدوير 90 درجة وقلب أفقي ورأسي، سطوع وتباين وتشبع وأبيض وأسود وسيبيا، رسم بفرشاة، إضافة نص، تراجع وإعادة، وتنزيل بصيغ PNG وJPG وWebP. أسماء الأزرار واضحة ولا يوجد زر غامض"),
    ("image-compressor-resizer", "ضغط وتصغير الصور: رفع صور متعددة، تحديد العرض أو النسبة والجودة، معاينة الحجم قبل وبعد، تنزيل النتيجة"),
    ("kanban-task-board", "لوحة مهام كانبان بثلاثة أعمدة، إضافة وتعديل وحذف البطاقات، نقلها بين الأعمدة بأزرار وبالسحب، تواريخ استحقاق وألوان، حفظ في localStorage وتصدير واستيراد JSON"),
    ("invoice-generator", "منشئ فواتير: بيانات البائع والعميل، بنود وضريبة وخصم، حساب تلقائي، معاينة وطباعة PDF من المتصفح، حفظ المسودات محليًا"),
    ("resume-builder-arabic", "منشئ سيرة ذاتية عربية: نماذج للخبرات والتعليم والمهارات، 3 قوالب، معاينة حية وطباعة PDF"),
    ("markdown-notes-editor", "محرر ملاحظات Markdown مع معاينة حية، بحث، حفظ تلقائي في localStorage وتنزيل الملفات"),
    ("whiteboard-drawing", "سبورة رسم: فرشاة وممحاة وأشكال وألوان وسُمك، تراجع وإعادة، حفظ كصورة PNG"),
    ("habit-and-pomodoro-tracker", "متتبع عادات يومية مع شبكة تقدم وسلاسل إنجاز، ومؤقت بومودورو مدمج وإحصاءات"),
    ("meme-poster-maker", "صانع ميمز وبوسترات: رفع صورة أو خلفية لونية، نصوص متعددة بخطوط وألوان وحدود، وتنزيل الصورة"),
    ("spreadsheet-lite", "جدول بيانات خفيف: شبكة خلايا قابلة للتحرير، صيغ SUM/AVERAGE/MIN/MAX/IF، تصدير CSV واستيراده"),
    ("json-regex-dev-toolbox", "صندوق أدوات المطور: منسّق JSON ومدقق، مختبر Regex مع إبراز التطابق، محول Base64 وURL"),
    ("flashcards-spaced-repetition", "بطاقات تعليمية بالتكرار المتباعد: مجموعات، مراجعة يومية بخوارزمية SM-2 مبسطة، إحصاءات، استيراد وتصدير"),
]

PROMPT = """You are an expert front-end engineer building ONE complete, genuinely useful Arabic (RTL) web app that will be embedded INSIDE an existing website page.
App: {idea}
The page already provides: the site's header/navigation, global CSS and a dark/gold theme. Use its classes and variables instead of inventing a design:
- classes: .card, .row (flex row of controls), button (gold primary), button.sec (secondary), label, input, select, textarea, .out (result box), .big (large result number), .badge, .divider
- CSS variables: --gold, --gold-bright, --gold-dim, --light, --dark. Dark background, light text.
Write ONLY these parts, in exactly this format, nothing else, no markdown fences:
TITLE: Arabic SEO title, at most 70 characters
H1: Arabic heading
DESCRIPTION: Arabic meta description, 110 to 160 characters
===BODY===
HTML fragment only (no <html>/<head>/<body>/<script>/<style>/<link>/<iframe>, no inline on* handlers, no external src/href). Start with an introductory paragraph of at least 80 words that starts with a quick answer, then the app UI. Every interactive element has an id. Clear Arabic labels, no ambiguous button names.
===CSS===
At most 60 lines of extra CSS for the app's own layout only (no @import, no url(http...)). Prefix selectors with .app.
===JS===
Vanilla JavaScript wiring the ids. No network (fetch/XMLHttpRequest/WebSocket), no eval/new Function, no document.cookie, no window.open, no URLs. localStorage in try/catch is fine. Every feature must really work, with empty/error states.
===FAQ===
Q: question
A: answer
(3 to 5 pairs)
Rules: write everything from scratch, never imitate a product's name or branding. Total under 30000 characters."""


def _section(text, name, nxt):
    m = re.search(rf"==={name}===\s*(.*?)\s*(?:==={nxt}===|\Z)", text, re.S)
    return m.group(1).strip() if m else ""


def _extract(text: str, slug: str) -> dict:
    text = re.sub(r"```[a-z]*", "", text or "")
    def head(key):
        m = re.search(rf"^{key}:\s*(.+)$", text, re.M)
        return m.group(1).strip() if m else ""
    faq = [{"q": q.strip(), "a": a.strip()} for q, a in re.findall(r"^Q:\s*(.+?)\s*^A:\s*(.+?)(?=^Q:|\Z)", _section(text, "FAQ", "END"), re.S | re.M)]
    return {"slug": slug, "title": head("TITLE")[:90], "h1": head("H1")[:80], "description": head("DESCRIPTION")[:200],
            "body_html": _section(text, "BODY", "CSS"), "css": _section(text, "CSS", "JS"),
            "script_js": _section(text, "JS", "FAQ"), "faq": faq[:5]}


IDEA_PROMPT = """A market scan found this product/project (category: {category}):
{desc}
Propose ONE original web app that serves the same everyday USER NEED, buildable as a fully client-side tool in a browser (HTML/JS/canvas/localStorage; no server, no accounts, no network, no AI model calls).
It must be useful to ordinary Arabic-speaking users searching for it. Never use the product's name.
If the need cannot be met client-side, answer exactly: SKIP
Otherwise answer in exactly two lines:
SLUG: english-kebab-case-name (2 to 4 words)
IDEA: Arabic description of the app and its concrete features (2 to 3 sentences)"""


def idea_from_opportunity(llm: dict, opp: dict, terms: list, deadline: float = None):
    """(slug, idea) for a client-side app serving the opportunity's need, or None. Never leaks the source name."""
    repo = opp["repo"]
    try:
        out = complete(IDEA_PROMPT.format(category=repo.get("category", ""), desc=(repo.get("description") or repo.get("full_name", ""))[:300]), llm, deadline)
    except Exception:
        return None
    if re.search(r"^\s*SKIP\b", out or "", re.I | re.M):
        return None
    slug = re.search(r"^SLUG:\s*([a-z0-9]+(?:-[a-z0-9]+){1,5})\s*$", out or "", re.M)
    idea = re.search(r"^IDEA:\s*(.+)$", out or "", re.M)
    if not slug or not idea or len(slug.group(1)) > 40:
        return None
    if privacy.leaks(slug.group(1) + " " + idea.group(1), terms):
        return None
    return slug.group(1), idea.group(1).strip()


def pick_idea(ledger):
    for slug, idea in IDEAS:
        if not ledger.is_known("app:" + slug):
            return slug, idea
    return None


def check(spec: dict) -> str:
    """Mirror of the site's gates (scripts/add_app.py). '' = ok, else the reason (fed back to the model)."""
    for k in ("slug", "title", "h1", "description", "body_html", "script_js"):
        if not isinstance(spec.get(k), str) or not spec[k].strip():
            return f"missing {k}"
    css = spec.get("css") or ""
    if len(spec["body_html"]) > 40000 or len(spec["script_js"]) > 40000 or len(css) > 9000:
        return "too large"
    faq = spec.get("faq")
    if not isinstance(faq, list) or not 3 <= len(faq) <= 6:
        return "faq must have 3-5 Q/A pairs"
    text = re.sub(r"<[^>]+>", " ", spec["body_html"])
    if len(text) < 300 or not re.search(r"[؀-ۿ]", text):
        return "body too thin or not Arabic"
    if re.search(r"<script|<iframe|<object|<embed|<link|<style|\son\w+\s*=|(src|href|action|data|poster)\s*=\s*[\"']?(https?:)?//", spec["body_html"], re.I):
        return "unsafe html in BODY"
    if re.search(r"@import|url\(\s*[\"']?\s*(https?:)?//|expression\(|</style", css, re.I):
        return "unsafe css"
    if re.search(r"fetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon|importScripts|import\s*\(|eval\s*\(|new Function|document\.cookie|window\.open|location\s*=|https?://|</script", spec["script_js"], re.I):
        return "unsafe js (network/eval/url)"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(spec["script_js"])
    res = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
    if res.returncode not in (0, 127):
        return "js syntax error: " + res.stderr[:200]
    return ""


def build(llm: dict, slug: str, idea: str, attempts: int = 4, deadline: float = None, reviewer=None):
    """Builder model -> local gates -> independent QA (browser + vision model) -> fix cycles.
    `reviewer(spec, idea)` returns visual.review()'s dict; None disables QA (offline tests)."""
    feedback, provider, last_ok = "", None, None
    for n in range(attempts):
        prompt = PROMPT.format(idea=idea, slug=slug) + (f"\nYour previous version was rejected. Fix ALL of these problems and return the complete result again in the same format:\n{feedback}" if feedback else "")
        try:
            spec = _extract(complete(prompt, llm, deadline), slug)
            provider = complete.used
        except Exception as exc:
            feedback = f"invalid answer ({str(exc)[:120]})"
            continue
        feedback = check(spec)
        if feedback:
            continue
        if not reviewer:
            return spec, provider, ""
        rev = reviewer(spec, idea)
        print(f"QA {slug} try {n + 1}: ok={rev['ok']} score={rev.get('score')} vision={rev.get('vision')} hard={len(rev.get('hard', []))}")
        if rev["ok"]:
            return spec, provider, ""
        if rev.get("env_error"):
            return None, provider, rev["problems"][0]          # broken QA environment: do not publish untested
        if not rev["hard"] and (rev.get("score") or 0) >= visual_accept():
            last_ok = spec
        feedback = "; ".join(rev["problems"])[:900]
    if last_ok is not None:
        return last_ok, provider, ""
    return None, provider, feedback


def visual_accept() -> float:
    from review import visual
    return visual.ACCEPT_AFTER_RETRIES


def publish(spec: dict, token: str, run_timeout: int = 900, live_timeout: int = 600, poll: int = 20) -> dict:
    ok, reason = preflight(token)
    if not ok:
        return {"state": "failed", "url": "", "reason": reason}
    started = datetime.now(timezone.utc) - timedelta(seconds=10)
    payload = {k: spec.get(k) for k in ("slug", "title", "h1", "description", "body_html", "css", "script_js", "faq")}
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
    url = f"{SITE_URL}/apps/{spec['slug']}.html"
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
