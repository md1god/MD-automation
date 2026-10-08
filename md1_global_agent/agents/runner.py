"""Runs one research mission with an autonomous OpenCode agent (free models, web access).

    python -m agents.runner opportunities     # what is most in demand / popular / profitable now
    python -m agents.runner channels          # free ways to publish and reach a real audience

The mission file defines the GOAL and the RULES. The agent decides where to look. This runner only:
runs the agent, extracts its JSON, checks that every cited URL is really reachable (anti-hallucination),
scales the agent's score by how much evidence survived, and merges into research/<mission>.json.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = {"opportunities": ROOT / "research" / "opportunities.json", "channels": ROOT / "research" / "channels.json"}
MIN_EVIDENCE = {"opportunities": 2, "channels": 1}
KEEP_DAYS = {"opportunities": 21, "channels": 365}
MAX_ITEMS = 300
JSON_BLOCK = re.compile(r"<<<JSON\s*(\{.*\})\s*JSON>>>", re.S)
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def now():
    return datetime.now(timezone.utc)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"items": []}


def live(url: str) -> bool:
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return False
    try:
        r = requests.get(url, timeout=15, allow_redirects=True, stream=True,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; md1-research/1.0)"})
        r.close()
        return r.status_code < 400 or r.status_code in (401, 403, 429)   # exists, just guarded
    except Exception:
        return False


def prompt_for(mission: str, known: list) -> str:
    text = (HERE / "missions" / f"{mission}.md").read_text(encoding="utf-8")
    return (f"{text}\n\nToday is {now().date()}.\n\nALREADY KNOWN (do not repeat):\n"
            + ("\n".join(f"- {n}" for n in known[:80]) or "- (nothing yet)"))


def run_agent(prompt: str, models: list, timeout: int = 600) -> tuple:
    errors = []
    for model in models:
        try:
            with tempfile.TemporaryDirectory() as empty:
                done = subprocess.run(["opencode", "run", "--model", f"opencode/{model}", prompt],
                                      capture_output=True, text=True, timeout=timeout, cwd=empty,
                                      env={**os.environ, "OPENCODE_ENABLE_EXA": "1"})
            text = ANSI.sub("", done.stdout or "")
            m = JSON_BLOCK.search(text)
            if m:
                return json.loads(m.group(1)), model
            errors.append(f"{model}: no JSON block (exit {done.returncode})")
        except Exception as exc:
            errors.append(f"{model}: {str(exc)[:150]}")
    raise RuntimeError(" | ".join(errors) or "no model")


def clean(mission: str, items: list) -> list:
    need, out = MIN_EVIDENCE[mission], []
    for it in items:
        try:
            urls = [u for u in dict.fromkeys(it.get("evidence", [])) if live(u)]
            if not it.get("name") or len(urls) < need:
                continue
            score = float(it["score"])
            score = max(0.0, min(100.0, score)) * min(1.0, len(urls) / 3)   # less proof -> lower score
            out.append({**it, "evidence": urls, "score": round(score, 1), "found_at": now().isoformat()})
        except Exception:
            continue
    return out


def merge(mission: str, old: list, new: list) -> list:
    keep_after = now() - timedelta(days=KEEP_DAYS[mission])
    byname = {o["name"].strip().lower(): o for o in old
              if datetime.fromisoformat(o["found_at"]) > keep_after}
    for n in new:
        byname[n["name"].strip().lower()] = n          # newest evidence replaces older
    return sorted(byname.values(), key=lambda o: o["score"], reverse=True)[:MAX_ITEMS]


def main(mission: str) -> int:
    if mission not in OUT:
        print(f"unknown mission {mission!r}; use: {', '.join(OUT)}")
        return 2
    with open(ROOT / "md1_global_agent" / "config.yaml", encoding="utf-8") as f:
        llm = yaml.safe_load(f).get("llm", {})
    sys.path.insert(0, str(ROOT / "md1_global_agent"))
    from builder import planner as P
    models = P._models_for("opencode_cli", llm, None)
    data = load(OUT[mission])
    try:
        result, model = run_agent(prompt_for(mission, [i["name"] for i in data["items"]]), models)
    except Exception as exc:
        print(f"RESEARCH FAILED ({mission}): {exc}")
        return 1
    fresh = clean(mission, result.get("items", []))
    print(f"{mission}: agent {model} proposed {len(result.get('items', []))}, {len(fresh)} survived the evidence check")
    if fresh:
        data["items"] = merge(mission, data["items"], fresh)
        OUT[mission].parent.mkdir(parents=True, exist_ok=True)
        OUT[mission].write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        for it in fresh[:5]:
            print(f"  {it['score']:5} {it['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
