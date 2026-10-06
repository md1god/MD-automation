"""Entry point: python main.py  (Dry Run by default, see config.yaml)"""
import os

import yaml

from agent import run
from builder.planner import make_plan
from notify import telegram


def main():
    with open("config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    opportunities, report = run(config)
    print(f"dry_run={config['dry_run']} | found={report['total']}")
    for o in opportunities[:10]:
        r, a = o["repo"], o["analysis"]
        print(f"{a['score']:5} | {o['mode']:16} | {r['full_name']} | {r['category']} | {a['license_note']}")
    print("Advice:", report["advice"])
    title, error = write_plan(opportunities, config.get("llm", {}))
    telegram.send(telegram.daily_report(
        config, opportunities, report, title, make_plan.used, error,
        "تفاصيل الخطة في Issue باسم Scout plan اليوم على الريبو." if title else ""))


def write_plan(opportunities, llm=None):
    """Plan the best buildable opportunity into plan.md using the first working LLM provider."""
    best = next((o for o in opportunities if "builder" in o), None)
    if not best:
        print("Plan: no opportunity passed the build threshold")
        return None, None
    try:
        text = make_plan(best, llm)
    except Exception as exc:
        print(f"Plan: failed ({exc})")
        return None, str(exc)
    title = f"{best['repo']['full_name']} ({best['mode']}, score {best['analysis']['score']})"
    with open("plan.md", "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n{best['repo']['url']}\n\n{text}\n")
    print(f"Plan: written to plan.md (via {make_plan.used})")
    return title, None


if __name__ == "__main__":
    main()
