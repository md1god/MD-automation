"""Telegram watcher for the mdm1.org pipelines.

mdm1.org has no Telegram secrets of its own; this repo does. Every run of this script lists the finished workflow runs of
md1god/MDM1.org since the last check and sends ONE Telegram message: every failure (with the failing step) plus a one-line
result for the pipelines that publish (REA Scout, Plan queue, Trend tool pages, Add app, Generate pages).
State (the last time it looked) is kept in .watch_state.json, restored/saved by the workflow through actions/cache.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
import yaml

from notify import telegram

REPO = os.getenv("WATCH_REPO", "md1god/MDM1.org")
STATE = os.getenv("WATCH_STATE", ".watch_state.json")
PUBLISHERS = ("REA Scout", "Plan queue", "Trend tool pages", "Add app", "Generate Pages", "Translate tools", "Publish multilingual")
IGNORE = ("Deploy to GitHub Pages", "pages-build-deployment", "Dependabot", "GitHub Advanced Security")
BAD = {"failure", "timed_out", "startup_failure"}


def api(path, **params):
    tok = os.getenv("SITES_PAT") or os.getenv("GITHUB_TOKEN") or ""
    h = {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {tok}"} if tok else {})}
    r = requests.get(f"https://api.github.com/repos/{REPO}/{path}", headers=h, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def why(run):
    try:
        for job in api(f"actions/runs/{run['id']}/jobs", per_page=30)["jobs"]:
            if job.get("conclusion") in BAD:
                step = next((s["name"] for s in job.get("steps", []) if s.get("conclusion") == "failure"), "")
                return f"{job['name']} / {step}".strip(" /")
    except Exception:
        pass
    return ""


def main():
    now = datetime.now(timezone.utc)
    try:
        since = parse(json.load(open(STATE))["checked_at"])
    except Exception:
        since = now - timedelta(hours=2)
    runs = api("actions/runs", per_page=100, status="completed")["workflow_runs"]
    fresh = [r for r in runs if parse(r["updated_at"]) > since and not any(i in r["name"] for i in IGNORE)]
    fails = [r for r in fresh if r["conclusion"] in BAD]
    done = [r for r in fresh if r["conclusion"] == "success" and any(p in r["name"] for p in PUBLISHERS)]
    if fails or done:
        lines = ["📡 mdm1.org — تقرير المسارات", ""]
        for r in fails:
            lines.append(f"❌ {r['name']}: {r['conclusion']} ({why(r) or 'راجع السجل'})\n   {r['html_url']}")
        for r in done:
            lines.append(f"✅ {r['name']}: نجح")
        channel = (yaml.safe_load(open("config.yaml", encoding="utf-8")) or {}).get("telegram_report_channel", "")   # the channel the bot already posts to
        if not telegram.send("\n".join(lines), channel):
            # Exit 0 on purpose: a red run would e-mail the owner every 30 minutes. The reason is in the log above and the next run retries.
            print("::warning::Telegram not delivered (see the lines above: set OWNER_CHAT_ID, or send /start to the bot); state not advanced")
            return 0
    else:
        print("nothing new")
    json.dump({"checked_at": now.isoformat()}, open(STATE, "w"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
