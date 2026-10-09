"""Turns a finished plan into a REAL multilingual page on mdm1.org and proves that it is live.

Flow: sanitize (no source identity) -> quality gate -> dispatch the site's `generate-pages.yml` ->
wait for that run to succeed -> fetch the live URL. "published" is reported only when the live page
answers 200 with our title; every other outcome is reported honestly as a failure.

The page is an honest "project under study" page (not a fake launched product). The site picks the
visitor's language from the device (navigator.languages) and offers a language selector.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import privacy

SITE_REPO = "md1god/mdm1.org"
WORKFLOW = "generate-pages.yml"
SITE_URL = "https://mdm1.org"
API = "https://api.github.com"
PENDING_DIR = Path(__file__).resolve().parents[1] / "memory" / "pending"

NOTICE = ("هذه خطة مشروع قيد الدراسة والتطوير ولم يُطلق بعد. "
          "نشارك تفاصيلها هنا لمتابعة التقدم خطوة بخطوة.")
MAX_BODY = 7000
MIN_BODY = 600
MIN_ARABIC_RATIO = 0.35


class PageRejected(Exception):
    """The plan failed a quality/privacy gate and must not be published."""


# ------------------------------------------------------------------ text preparation

def md_to_text(md: str) -> str:
    """Markdown -> plain paragraphs (the site escapes HTML and wraps every line in <p>)."""
    out = []
    for line in (md or "").splitlines():
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        line = re.sub(r"^\s*[-*+]\s+", "• ", line)
        line = re.sub(r"[*_`]{1,3}", "", line)
        line = re.sub(r"^\s*\|?[-:\s|]{3,}\|?\s*$", "", line)
        line = line.replace("|", " · ").strip()
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _clean_name(value: str) -> str:
    value = re.split(r"\s*[\(\[]|\s+—\s+|\s+-\s+(?=\S)", value.strip(), maxsplit=1)[0]
    return value.strip(" \"'`*:؛،.")[:40]


def extract_name_and_pitch(text: str):
    name = pitch = ""
    for line in text.splitlines():
        m = re.search(r"(?:الاسم(?: المقترح)?|Suggested name|Name)\s*[:：]\s*(.+)", line, re.I)
        if m and not name:
            name = _clean_name(m.group(1))
        m = re.search(r"(?:الجملة التسويقية|جملة التعريف|العرض التسويقي|Pitch|one-line pitch)\s*[:：]\s*(.+)",
                      line, re.I)
        if m and not pitch:
            pitch = m.group(1).strip(" \"'`*")
    return name, pitch


def _arabic_ratio(text: str) -> float:
    letters = re.findall(r"[^\W\d_]", text)
    return len(re.findall(r"[؀-ۿ]", text)) / len(letters) if letters else 0.0


def build_payload(plan_md: str, pub_id: str, terms: list, ledger_key: str = "") -> dict:
    """Sanitized, gated page content. Raises PageRejected with a human-readable reason."""
    text = privacy.sanitize(md_to_text(plan_md), terms)
    name, pitch = extract_name_and_pitch(text)
    name = "" if privacy.HIDDEN in name else name
    pitch = "" if privacy.HIDDEN in pitch else pitch
    title = f"{name} — خطة مشروع قيد الدراسة" if name else f"خطة مشروع جديد · {pub_id}"
    description = (pitch or "خطة أصلية لمشروع رقمي جديد: الجمهور، الفكرة، النموذج الربحي وخطة الانتشار.")[:160]
    body = f"{NOTICE}\n\n{text}"[:MAX_BODY]
    payload = {"id": pub_id, "ledger_key": ledger_key, "title": title, "description": description,
               "body": body, "translations": {}}
    ok, reason = quality_gate(payload, terms)
    if not ok:
        raise PageRejected(reason)
    return payload


def quality_gate(payload: dict, terms: list):
    whole = "\n".join((payload["title"], payload["description"], payload["body"]))
    found = privacy.leaks(whole, terms)
    if found:
        return False, f"تسريب هوية المصدر ({len(found)} عنصر) — تم إيقاف النشر"
    if len(payload["body"]) < MIN_BODY:
        return False, "نص الخطة قصير جدًا لنشره"
    if not 3 <= len(payload["title"]) <= 120:
        return False, "عنوان الصفحة غير صالح"
    if _arabic_ratio(whole) < MIN_ARABIC_RATIO:
        return False, "نص الخطة ليس عربيًا بما يكفي"
    if re.search(r"<\s*script|javascript:", whole, re.I):
        return False, "النص يحتوي على كود غير مسموح"
    return True, ""


# ------------------------------------------------------------------ retry queue (sanitized only)

def save_pending(payload: dict) -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    (PENDING_DIR / f"{payload['id']}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def load_pending() -> list:
    if not PENDING_DIR.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PENDING_DIR.glob("*.json"))]


def drop_pending(pub_id: str) -> None:
    (PENDING_DIR / f"{pub_id}.json").unlink(missing_ok=True)


# ------------------------------------------------------------------ dispatch + verification

def _headers(token: str, raw: bool = False) -> dict:
    return {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "md1-scout"}


def _js_escape(value: str) -> str:
    """Mirror of escapeHtml() in the site's build-pages.js."""
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def _fail(reason: str) -> dict:
    return {"state": "failed", "url": "", "reason": reason}


def preflight(token: str):
    """(ok, reason). Fails loudly when SITES_PAT is missing, expired or lacks permission."""
    if not token:
        return False, "سر SITES_PAT غير موجود في المستودع"
    try:
        r = requests.get(f"{API}/repos/{SITE_REPO}", headers=_headers(token), timeout=30)
    except requests.RequestException as exc:
        return False, f"تعذر الوصول إلى GitHub ({type(exc).__name__})"
    if r.status_code == 401:
        return False, "SITES_PAT منتهي أو غير صالح (401) — أنشئ توكن جديد"
    if r.status_code in (403, 404):
        return False, f"SITES_PAT لا يملك وصولًا إلى {SITE_REPO} ({r.status_code})"
    if not r.ok:
        return False, f"فحص الصلاحيات فشل ({r.status_code})"
    return True, ""


def publish(payload: dict, token: str, run_timeout: int = 600, live_timeout: int = 300, poll: int = 15) -> dict:
    """Dispatch the site workflow, wait for it, verify the live page. Never raises."""
    ok, reason = preflight(token)
    if not ok:
        return _fail(reason)
    started = datetime.now(timezone.utc) - timedelta(seconds=10)
    inputs = {"scout_id": payload["id"], "scout_title": payload["title"],
              "scout_description": payload["description"], "scout_body": payload["body"],
              "scout_translations": json.dumps(payload.get("translations") or {}, ensure_ascii=False)}
    try:
        r = requests.post(f"{API}/repos/{SITE_REPO}/actions/workflows/{WORKFLOW}/dispatches",
                          headers=_headers(token), json={"ref": "main", "inputs": inputs}, timeout=30)
    except requests.RequestException as exc:
        return _fail(f"إرسال الـ workflow فشل ({type(exc).__name__})")
    if r.status_code == 403:
        return _fail("SITES_PAT يحتاج صلاحية Actions: write على mdm1.org")
    if r.status_code != 204:
        return _fail(f"إرسال الـ workflow فشل ({r.status_code}: {r.text[:120]})")

    run = None
    deadline = time.time() + run_timeout
    while time.time() < deadline:
        time.sleep(poll)
        try:
            runs = requests.get(f"{API}/repos/{SITE_REPO}/actions/workflows/{WORKFLOW}/runs",
                                headers=_headers(token), params={"event": "workflow_dispatch", "per_page": 5},
                                timeout=30).json().get("workflow_runs", [])
        except (requests.RequestException, ValueError):
            continue
        fresh = [x for x in runs if datetime.fromisoformat(x["created_at"].replace("Z", "+00:00")) >= started]
        if fresh:
            run = fresh[0]                       # API lists newest first
            if run["status"] == "completed":
                break
    if not run or run["status"] != "completed":
        return _fail("انتهت مهلة انتظار workflow موقع mdm1.org")
    if run["conclusion"] != "success":
        return _fail(f"workflow موقع mdm1.org انتهى بنتيجة {run['conclusion']}")

    try:
        reg = requests.get(f"{API}/repos/{SITE_REPO}/contents/pages-registry.json", params={"ref": "main"},
                           headers=_headers(token, raw=True), timeout=30).json()
        entry = next(e for e in reversed(reg) if e.get("scoutId") == payload["id"])
        slug = str(entry["slug"])
    except (requests.RequestException, ValueError, StopIteration, TypeError):
        return _fail("تعذر تحديد رقم الصفحة المنشورة")
    url = f"{SITE_URL}/pages/{slug}.html"
    needle = _js_escape(payload["title"])
    deadline = time.time() + live_timeout
    while time.time() < deadline:
        try:
            page = requests.get(url, timeout=30, headers={"Cache-Control": "no-cache"})
            if page.status_code == 200 and needle in page.text:
                return {"state": "published", "url": url, "reason": ""}
        except requests.RequestException:
            pass
        time.sleep(poll)
    return _fail(f"تم إرسال الصفحة لكنها لم تظهر على {url} بعد")


def env_token() -> str:
    return os.getenv("SITES_PAT", "").strip()
