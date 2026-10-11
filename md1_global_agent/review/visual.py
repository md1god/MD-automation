"""Independent QA role: render the finished app page in a real browser, then judge it.

Two layers, deliberately not trusting the builder model:
  1. Objective checks (no model): page loads offline, no JS errors, enough interactive elements, the screenshot
     is not blank/flat, nothing overflows horizontally on a phone viewport.
  2. A free VISION model looks at the screenshots (desktop + phone, before and after clicking every button)
     and reports what is broken or confusing. Providers are tried free-first: OpenRouter free vision models,
     Groq vision models, then GitHub Models. If no vision model answers, layer 1 still decides.
Result: review(spec) -> {"ok": bool, "problems": [str], "vision": "used"|"unavailable"}.
The problems are fed back to the BUILDER model so it can fix them.
"""
import base64
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import requests

from builder import planner

MIN_ELEMENTS = 3
MIN_SCORE = 6
ACCEPT_AFTER_RETRIES = 5     # last attempt: no hard problem and vision score >= this is good enough


def _render_page(spec: dict, site_dir: str) -> Path:
    """Write the page with the SITE'S OWN template next to the real css/js so it looks exactly as published."""
    scripts = str(Path(site_dir) / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    os.environ.pop("APP_JSON", None)
    import add_app                                    # importing is harmless: main() returns without APP_JSON
    page = Path(site_dir) / "apps" / f"_preview-{spec['slug']}.html"
    page.parent.mkdir(exist_ok=True)
    data = dict(spec, css=spec.get("css") or "")
    page.write_text(add_app.page(data), encoding="utf-8")
    return page


def _shots(page: Path) -> dict:
    """{'problems': [...], 'images': {name: png_bytes}} using headless Chromium, fully offline."""
    from playwright.sync_api import sync_playwright
    problems, images = [], {}
    with sync_playwright() as pw:
        exe = os.getenv("CHROMIUM_PATH") or None
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        errors = []
        for label, size in (("desktop", {"width": 1100, "height": 900}), ("phone", {"width": 390, "height": 800})):
            ctx = browser.new_context(viewport=size)
            p = ctx.new_page()
            p.on("pageerror", lambda e: errors.append(str(e)[:160]))
            p.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:") else r.abort())
            p.goto(page.resolve().as_uri())
            p.wait_for_timeout(500)
            n = p.evaluate("document.querySelectorAll('.app button,.app input,.app select,.app textarea,.app canvas').length")
            if n < MIN_ELEMENTS:
                problems.append(f"only {n} interactive elements found")
            if label == "phone":
                over = p.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                if over > 24:
                    problems.append(f"page overflows horizontally on a phone by {over}px")
            images[f"{label}-before"] = p.locator(".app").first.screenshot() if p.locator(".app").count() else p.screenshot()
            for b in p.query_selector_all(".app button")[:30]:
                try:
                    b.click(timeout=700, force=True)
                except Exception:
                    pass
            p.wait_for_timeout(300)
            images[f"{label}-after"] = p.locator(".app").first.screenshot() if p.locator(".app").count() else p.screenshot()
            ctx.close()
        browser.close()
    if errors:
        problems.append("JavaScript errors: " + " | ".join(sorted(set(errors))[:3]))
    return {"problems": problems, "images": images}


def _flat(png: bytes) -> bool:
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB").resize((96, 96))
    colors = im.getcolors(maxcolors=96 * 96) or []
    top = max((c for c, _ in colors), default=0)
    return len(colors) < 12 or top / (96 * 96) > 0.985


VISION_PROMPT = """You are a strict QA reviewer for a free Arabic web app embedded in a website with a dark gold theme.
You are given screenshots of the app's area: desktop and phone, before and after every button was clicked once.
Judge ONLY what you can actually see. Do not assume anything works.
The app is meant to: {idea}
Answer ONLY with JSON: {{"works": true/false, "score": 1-10, "problems": ["short concrete problem", ...], "missing": ["important missing feature", ...]}}
Mark works=false if the area is blank, controls are missing or unreadable, text overlaps, or buttons have unclear names."""


def _vision_candidates():
    out = []
    key = planner._key_for("openrouter", planner.PROVIDERS["openrouter"])
    if key:
        try:
            data = requests.get(planner.PROVIDERS["openrouter"]["models_url"], timeout=30).json().get("data", [])
            for m in data:
                price = m.get("pricing") or {}
                ins = (m.get("architecture") or {}).get("input_modalities") or []
                if "image" in ins and str(price.get("prompt")) == "0" and str(price.get("completion")) == "0":
                    out.append(("openrouter", m["id"], key))
        except Exception:
            pass
    key = planner._key_for("groq", planner.PROVIDERS["groq"])
    if key:
        try:
            ids = [m["id"] for m in requests.get(planner.PROVIDERS["groq"]["models_url"], headers={"Authorization": f"Bearer {key}"}, timeout=30).json().get("data", [])]
            out += [("groq", i, key) for i in ids if re.search(r"vision|llama-4|scout|maverick", i, re.I)]
        except Exception:
            pass
    key = planner._key_for("github", planner.PROVIDERS["github"])
    if key:
        out.append(("github", "openai/gpt-4o", key))
    return out[:8]


def _ask_vision(images: dict, idea: str):
    content = [{"type": "text", "text": VISION_PROMPT.format(idea=idea[:300])}]
    for name, png in images.items():
        content.append({"type": "text", "text": f"Screenshot: {name}"})
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}})
    for provider, model, key in _vision_candidates():
        spec = planner.PROVIDERS[provider]
        try:
            r = requests.post(spec["url"], headers={"Authorization": f"Bearer {key}", "content-type": "application/json", **spec.get("extra_headers", {})},
                              json={"model": model, "max_tokens": 700, "messages": [{"role": "user", "content": content}]}, timeout=120)
            if not r.ok:
                continue
            text = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            m = re.search(r"\{.*\}", text, re.S)
            verdict = json.loads(m.group(0)) if m else None
            if isinstance(verdict, dict) and "works" in verdict:
                verdict["_model"] = f"{provider}/{model}"
                return verdict
        except Exception:
            continue
    return None


def review(spec: dict, idea: str, site_dir: str) -> dict:
    """Never raises: a broken QA environment must not publish untested work silently, nor block forever."""
    try:
        page = _render_page(spec, site_dir)
        shots = _shots(page)
    except Exception as exc:
        return {"ok": False, "hard": ["QA env"], "soft": [], "score": None, "problems": [f"QA could not render the page: {type(exc).__name__}: {str(exc)[:160]}"], "vision": "unavailable", "env_error": True}
    finally:
        try:
            Path(site_dir, "apps", f"_preview-{spec['slug']}.html").unlink()
        except Exception:
            pass
    hard = list(shots["problems"])
    if any(_flat(png) for name, png in shots["images"].items() if name.endswith("before")):
        hard.append("the rendered app area is blank/flat")
    verdict = _ask_vision(shots["images"], idea)
    soft, score = [], None
    if verdict:
        soft += [str(x) for x in (verdict.get("problems") or [])][:6]
        soft += ["missing: " + str(x) for x in (verdict.get("missing") or [])][:3]
        try:
            score = float(verdict.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        if not verdict.get("works", False):
            score = min(score, 3.0)
            hard.append("vision reviewer says the app does not work as shown")
    ok = not hard and (score is None or score >= MIN_SCORE)
    return {"ok": ok, "hard": hard, "soft": soft, "score": score, "problems": hard + soft,
            "vision": "used" if verdict else "unavailable", "model": (verdict or {}).get("_model", "")}
