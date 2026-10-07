"""Entry point: python main.py  (Dry Run by default, see config.yaml)"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from agent import run
from builder.planner import make_plan
from notify import telegram


PLANNED_FILE = Path("memory/planned.json")


def _load_planned() -> dict:
    return json.loads(PLANNED_FILE.read_text(encoding="utf-8")) if PLANNED_FILE.exists() else {}


def _recently_planned(planned: dict, name: str, days: int) -> bool:
    when = planned.get(name)
    if not when:
        return False
    return (datetime.now(timezone.utc) - datetime.fromisoformat(when)).days < days


def main():
    with open("config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    opportunities, report = run(config)
    print(f"dry_run={config['dry_run']} | found={report['total']}")
    for o in opportunities[:10]:
        r, a = o["repo"], o["analysis"]
        print(f"{a['score']:5} | {o['mode']:16} | {r['full_name']} | {r['category']} | {a['license_note']}")
    print("Advice:", report["advice"])
    title, error = write_plan(opportunities, config.get("llm", {}), config.get("replan_days", 30))
    telegram.send(channel=config.get("telegram_report_channel", ""), text=telegram.daily_report(
        config, opportunities, report, title, make_plan.used, error,
        "تفاصيل الخطة في Issue باسم Scout plan اليوم على الريبو." if title else ""))


def write_plan(opportunities, llm=None, replan_days=30):
    """Plan the best buildable opportunity NOT planned in the last `replan_days` days into plan.md."""
    planned = _load_planned()
    buildable = [o for o in opportunities if "builder" in o]
    best = next((o for o in buildable
                 if not _recently_planned(planned, o["repo"]["full_name"], replan_days)), None)
    if not best:
        print("Plan: no NEW opportunity today" if buildable else "Plan: no opportunity passed the build threshold")
        return None, None
    try:
        text = make_plan(best, llm)
    except Exception as exc:
        print(f"Plan: failed ({exc})")
        return None, str(exc)
    title = f"{best['repo']['full_name']} ({best['mode']}, score {best['analysis']['score']})"
    with open("plan.md", "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n{best['repo']['url']}\n\n{text}\n")
    planned[best["repo"]["full_name"]] = datetime.now(timezone.utc).isoformat()
    PLANNED_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLANNED_FILE.write_text(json.dumps(planned, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Plan: written to plan.md (via {make_plan.used})")
    return title, None


if __name__ == "__main__":
    main()
