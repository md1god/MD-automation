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

NOTICE = ("خطة تنفيذ كاملة لمشروع رقمي جديد: الفكرة والجمهور والمنتج والنموذج الربحي وخطة الانتشار والمخاطر. "
          "المشروع قيد البناء ولم يُطلق بعد.")
MAX_BODY = 7000
MIN_BODY = 2500
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
    title = f"{name} — خطة مشروع كاملة" if name else f"خطة مشروع جديد · {pub_id}"
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
    if "·" in payload["title"] and payload["title"].startswith("خطة مشروع جديد"):
        return False, "الخطة بلا اسم مقترح — غير مكتملة"
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


IN_FLIGHT = ("queued", "in_progress", "waiting", "pending", "requested")


def registry_slug(token: str, scout_id: str) -> str:
    """Slug of the page the site already holds for `scout_id` ('' if none).

    The site registry is the source of truth: a workflow run can look failed or timed out while its page
    was in fact committed, and the site refuses to create a second page for the same scout_id.
    """
    try:
        reg = requests.get(f"{API}/repos/{SITE_REPO}/contents/pages-registry.json", params={"ref": "main"},
                           headers=_headers(token, raw=True), timeout=30).json()
        entry = next(e for e in reversed(reg) if e.get("scoutId") == scout_id)
        return str(entry["slug"])
    except (requests.RequestException, ValueError, StopIteration, TypeError, KeyError):
        return ""


def _dispatch(payload: dict, token: str):
    """Start the site workflow. Returns (started_at, error_reason_or_None)."""
    started = datetime.now(timezone.utc) - timedelta(seconds=10)
    inputs = {"scout_id": payload["id"], "scout_title": payload["title"],
              "scout_description": payload["description"], "scout_body": payload["body"],
              "scout_translations": json.dumps(payload.get("translations") or {}, ensure_ascii=False)}
    try:
        r = requests.post(f"{API}/repos/{SITE_REPO}/actions/workflows/{WORKFLOW}/dispatches",
                          headers=_headers(token), json={"ref": "main", "inputs": inputs}, timeout=30)
    except requests.RequestException as exc:
        return started, f"إرسال الـ workflow فشل ({type(exc).__name__})"
    if r.status_code == 403:
        return started, "SITES_PAT يحتاج صلاحية Actions: write على mdm1.org"
    if r.status_code != 204:
        return started, f"إرسال الـ workflow فشل ({r.status_code}: {r.text[:120]})"
    return started, None


def _wait_run(token: str, started, run_timeout: int, grace: int, poll: int, no_run_after: int):
    """Follow the run created after `started`. Returns (run | None, state).

    state: 'completed' | 'not_started' (dispatch never produced a run) | 'still_running'.
    The site's `pages` concurrency group is shared with deploy.yml, so a run can wait in the queue for a long
    time: past `run_timeout` we keep waiting (up to `grace` more) as long as the run is really queued/running.
    """
    t0 = time.time()
    soft, hard = t0 + run_timeout, t0 + run_timeout + grace
    run = None
    while True:
        if run and run["status"] == "completed":
            return run, "completed"
        now = time.time()
        if now >= hard or (now >= soft and not (run and run["status"] in IN_FLIGHT)):
            break
        if not run and now - t0 >= no_run_after:
            return None, "not_started"
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
    return run, ("still_running" if run else "not_started")


def _verify_live(slug: str, payload: dict, live_timeout: int, poll: int) -> dict:
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


def publish(payload: dict, token: str, run_timeout: int = 600, live_timeout: int = 300, poll: int = 15,
            grace: int = 600, no_run_after: int = 240) -> dict:
    """Dispatch the site workflow, wait for it, verify the live page. Never raises.

    Safe to repeat for the same payload: the site dedups by scout_id, and the registry is checked first.
    """
    ok, reason = preflight(token)
    if not ok:
        return _fail(reason)

    slug = registry_slug(token, payload["id"])    # an earlier attempt may already have produced the page
    if slug:
        return _verify_live(slug, payload, live_timeout, poll)

    run, state = None, "not_started"
    for attempt in (1, 2):
        started, err = _dispatch(payload, token)
        if err:
            return _fail(err)
        run, state = _wait_run(token, started, run_timeout, grace, poll, no_run_after)
        if attempt == 1 and (state == "not_started"
                             or (state == "completed" and run["conclusion"] == "cancelled")):
            continue                              # lost dispatch / replaced in the shared concurrency queue
        break

    slug = registry_slug(token, payload["id"])    # even a "failed" or timed-out run may have committed the page
    if not slug:
        if state == "still_running":
            return _fail("انتهت مهلة انتظار workflow موقع mdm1.org (ما زال في الطابور أو قيد التشغيل)")
        if state == "not_started":
            return _fail("workflow موقع mdm1.org لم يبدأ بعد الإرسال")
        if run["conclusion"] != "success":
            return _fail(f"workflow موقع mdm1.org انتهى بنتيجة {run['conclusion']}")
        return _fail("تعذر تحديد رقم الصفحة المنشورة")
    return _verify_live(slug, payload, live_timeout, poll)


def env_token() -> str:
    return os.getenv("SITES_PAT", "").strip()
