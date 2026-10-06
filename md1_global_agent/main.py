"""Entry point: python main.py  (Dry Run by default, see config.yaml)"""
import os

import yaml

from agent import run
from builder.planner import make_plan


def main():
    with open("config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    opportunities, report = run(config)
    print(f"dry_run={config['dry_run']} | found={report['total']}")
    for o in opportunities[:10]:
        r, a = o["repo"], o["analysis"]
        print(f"{a['score']:5} | {o['mode']:16} | {r['full_name']} | {r['category']} | {a['license_note']}")
    print("Advice:", report["advice"])
    write_plan(opportunities)


def write_plan(opportunities):
    """If ANTHROPIC_API_KEY is set, plan the best buildable opportunity into plan.md."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Plan: skipped (no ANTHROPIC_API_KEY)")
        return
    best = next((o for o in opportunities if "builder" in o), None)
    if not best:
        print("Plan: no opportunity passed the build threshold")
        return
    try:
        text = make_plan(best)
    except Exception as exc:
        print(f"Plan: failed ({exc})")
        return
    title = f"{best['repo']['full_name']} ({best['mode']}, score {best['analysis']['score']})"
    with open("plan.md", "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n{best['repo']['url']}\n\n{text}\n")
    print("Plan: written to plan.md")


if __name__ == "__main__":
    main()
