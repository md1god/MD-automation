"""Unattended growth loop: select a project -> write the post -> publish to OWN channels -> measure -> learn.

Run from md1_global_agent/:   python -m growth.engine [--dry]
Channels switch themselves off when their secret is missing. State lives in growth/state.json
(committed straight to main by the workflow - no pull request, no manual step).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "state.json"
# Posts that could read as financial promotion are never sent (checked on the FINAL text).
BANNED = re.compile(
    r"(guarantee|risk[- ]free|\b\d+\s?x\b|to the moon|get rich|profit|\breturns?\b|\bapy\b|passive income|"
    r"financial advice|buy now|ربح مضمون|مضمون|أرباح|ارباح|عائد|اغتن|ثراء|استثمر الآن|ضاعف)", re.I)


def now() -> datetime:
    return datetime.now(timezone.utc)


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"posts": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _age(post: dict) -> timedelta:
    return now() - datetime.fromisoformat(post["ts"])


# ---------------------------------------------------------------- selection
def stats(state: dict) -> dict:
    """Per (project|angle): number of measured posts and mean engagement score."""
    out: dict = {}
    for p in state["posts"]:
        if p.get("score") is None:
            continue
        s = out.setdefault(f'{p["project"]}|{p["angle"]}', {"n": 0, "sum": 0.0})
        s["n"] += 1
        s["sum"] += p["score"]
    return out


def pick(cfg: dict, state: dict, rng: random.Random):
    """Weighted UCB: untried angles first, then winners, with a cooldown per project."""
    st = stats(state)
    means = [s["sum"] / s["n"] for s in st.values() if s["n"]]
    top = max(means) if means and max(means) > 0 else 1.0
    total = sum(s["n"] for s in st.values())
    best, best_val = None, -1.0
    for proj in cfg["projects"]:
        if proj.get("enabled", True) is False:
            continue
        if any(p["project"] == proj["id"] and _age(p) < timedelta(days=cfg.get("cooldown_days", 3))
               for p in state["posts"]):
            continue
        for angle in proj["angles"]:
            s = st.get(f'{proj["id"]}|{angle["id"]}')
            n = s["n"] if s else 0
            norm = (s["sum"] / s["n"]) / top if n else 1.0   # untried = optimistic
            bonus = cfg.get("explore", 0.6) * math.sqrt(math.log(total + 2) / (n + 1))
            posted = sum(1 for p in state["posts"] if p["project"] == proj["id"] and p["angle"] == angle["id"])
            val = proj.get("weight", 1.0) * (norm + bonus) / (1 + 0.15 * posted) * (1 + 0.05 * rng.random())
            if val > best_val:
                best, best_val = (proj, angle), val
    return best


# ---------------------------------------------------------------- writing
def complete(prompt: str, llm: dict) -> str:
    """First working provider from config.yaml's llm section (same chain the planner uses)."""
    from builder import planner as P
    errors = []
    for name in llm.get("providers", ["opencode_cli", "openrouter", "groq", "github"]):
        spec = P.PROVIDERS.get(name)
        if not spec:
            continue
        key = P._key_for(name, spec)
        if spec["style"] != "cli" and not key:
            errors.append(f"{name}: no key")
            continue
        for model in P._models_for(name, llm, key) or []:
            try:
                return (P._call_cli(model, prompt) if spec["style"] == "cli"
                        else P._call_http(name, model, prompt, key)).strip()
            except Exception as exc:  # next model
                errors.append(f"{name}/{model}: {str(exc)[:120]}")
    raise RuntimeError(" | ".join(errors) or "no provider")


def link(proj: dict, angle: dict, channel: str) -> str:
    sep = "&" if "?" in proj["url"] else "?"
    return f'{proj["url"]}{sep}utm_source={channel}&utm_medium=social&utm_campaign={proj["id"]}-{angle["id"]}'


def _prompt(proj, angle, kind, lang):
    language = "Arabic (clear Egyptian-friendly Modern Standard Arabic)" if lang == "ar" else "English"
    shape = ("A short Telegram post: 3-5 sentences, plain text, at most 2 emojis, no hashtags."
             if kind == "telegram" else
             "A dev.to article of 250-400 words in Markdown with a title. First line must be 'TITLE: <title>'.")
    return (f"You write for the project '{proj['name']}'. Audience: {proj['audience']}.\n"
            f"Language: {language}.\nAngle: {angle['brief']}.\n{shape}\n"
            "Use ONLY these facts and add no other claims, numbers, dates, partnerships or features:\n- "
            + "\n- ".join(proj["facts"]) +
            "\nRules: no price talk, no returns, profit, investment advice, urgency or guarantees. "
            "Do not include any URL (it is added automatically). Be honest and useful, not promotional.")


def compose(proj, angle, kind, lang, llm):
    """Return (title, body, how). Falls back to a plain fact-based text if the LLM fails or is unsafe."""
    try:
        text = complete(_prompt(proj, angle, kind, lang), llm)
        title = None
        if kind == "devto":
            m = re.match(r"\s*TITLE:\s*(.+)", text)
            title = m.group(1).strip() if m else f'{proj["name"]}: {angle["id"]}'
            text = re.sub(r"^\s*TITLE:.*\n?", "", text, count=1).strip()
        if not BANNED.search((title or "") + text):
            return title, text, "llm"
        print(f"compose: LLM text rejected by safety filter ({proj['id']}/{angle['id']}/{kind})")
    except Exception as exc:
        print(f"compose: LLM unavailable ({str(exc)[:200]})")
    text = "\n".join(proj["facts"])
    return (f'{proj["name"]}' if kind == "devto" else None), text, "facts"


# ---------------------------------------------------------------- publishing
def _tg_token() -> str:
    raw = "".join(os.getenv("TELEGRAM_BOT_TOKEN", "").split())
    return raw[3:] if raw.lower().startswith("bot") and ":" in raw[3:] else raw


def publish_telegram(ch: dict, text: str):
    token = _tg_token()
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": ch["chat"], "text": text}, timeout=30)
    if not r.ok:
        return None, None, f"{r.status_code}: {r.text[:150]}"
    mid = r.json()["result"]["message_id"]
    return str(mid), f'https://t.me/{ch["chat"].lstrip("@")}/{mid}', None


def publish_devto(ch: dict, title: str, body: str, canonical: str):
    r = requests.post("https://dev.to/api/articles", timeout=30,
                      headers={"api-key": os.environ["DEVTO_API_KEY"]},
                      json={"article": {"title": title, "body_markdown": body, "published": True,
                                        "tags": ch.get("tags", [])[:4], "canonical_url": canonical}})
    if not r.ok:
        return None, None, f"{r.status_code}: {r.text[:150]}"
    j = r.json()
    return str(j["id"]), j["url"], None


def eligible(name: str, ch: dict, state: dict):
    """(ok, reason) - secret present, enabled, and within the channel's rate cap."""
    if not ch.get("enabled", True):
        return False, "disabled"
    secret = {"telegram": "TELEGRAM_BOT_TOKEN", "devto": "DEVTO_API_KEY"}[name]
    if not os.getenv(secret, "").strip():
        return False, f"secret {secret} not set"
    mine = [p for p in state["posts"] if p["channel"] == name and not p.get("dry")]
    if name == "telegram" and sum(1 for p in mine if _age(p) < timedelta(days=1)) >= ch.get("max_per_day", 1):
        return False, "daily cap reached"
    if name == "devto" and any(_age(p) < timedelta(days=ch.get("min_days_between", 7)) for p in mine):
        return False, "weekly cap reached"
    return True, ""


# ---------------------------------------------------------------- measuring
def measure(state: dict) -> None:
    """dev.to is the one channel that reports numbers; they drive what gets picked next."""
    key = os.getenv("DEVTO_API_KEY", "").strip()
    if not key or not any(p["channel"] == "devto" for p in state["posts"]):
        return
    try:
        r = requests.get("https://dev.to/api/articles/me/published?per_page=100",
                         headers={"api-key": key}, timeout=30)
        r.raise_for_status()
    except Exception as exc:
        print(f"measure: skipped ({str(exc)[:120]})")
        return
    by_id = {str(a["id"]): a for a in r.json()}
    for p in state["posts"]:
        a = by_id.get(p.get("ref")) if p["channel"] == "devto" else None
        if a:
            p["score"] = (a.get("page_views_count", 0) + 10 * a.get("public_reactions_count", 0)
                          + 20 * a.get("comments_count", 0))


# ---------------------------------------------------------------- main
def run(dry: bool = False, seed=None) -> int:
    with open(HERE / "growth.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    with open(HERE.parent / "config.yaml", encoding="utf-8") as f:
        llm = yaml.safe_load(f).get("llm", {})
    dry = dry or cfg.get("dry_run", False)
    state = load_state()
    measure(state)
    choice = pick(cfg, state, random.Random(seed))
    if not choice:
        print("growth: nothing to promote today (all projects are in cooldown)")
        save_state(state)
        return 0
    proj, angle = choice
    print(f"growth: selected {proj['id']} / {angle['id']}  dry={dry}")
    attempted = failed = 0
    for name, ch in cfg["channels"].items():
        ok, why = eligible(name, ch, state)
        if not ok:
            print(f"  {name}: skipped ({why})")
            continue
        title, body, how = compose(proj, angle, name, ch.get("language", "en"), llm)
        url = link(proj, angle, name)
        full = f"{body}\n\n{url}"
        if BANNED.search(full):
            print(f"  {name}: blocked by safety filter")
            continue
        attempted += 1
        if dry:
            print(f"  {name}: DRY-RUN ({how})\n--- {title or ''}\n{full}\n---")
            ref, pub, err = None, None, None
        elif name == "telegram":
            ref, pub, err = publish_telegram(ch, full)
        else:
            ref, pub, err = publish_devto(ch, title or proj["name"], full, url)
        if err:
            failed += 1
            print(f"  {name}: FAILED {err}")
            continue
        print(f"  {name}: published via {how} -> {pub or '(dry)'}")
        state["posts"].append({"ts": now().isoformat(), "project": proj["id"], "angle": angle["id"],
                               "channel": name, "ref": ref, "url": pub, "how": how,
                               **({"dry": True} if dry else {})})
    state["posts"] = [p for p in state["posts"] if not p.get("dry")]
    save_state(state)
    return 1 if attempted and failed == attempted else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    sys.exit(run(ap.parse_args().dry))
