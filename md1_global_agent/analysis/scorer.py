"""Investigator + Strategist roles: scores each opportunity 0-100."""
import math
from datetime import datetime, timezone

from .license_check import check as license_check


def _days_since(iso):
    if not iso:
        return 9999
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).days


def score(repo: dict, config: dict, memory: dict):
    ok, license_note = license_check(repo, config.get("allowed_licenses", []))
    popularity = min(30, math.log10(max(repo["stars"], 1)) * 8)       # audience proof
    activity_days = _days_since(repo["pushed_at"])
    activity = 25 if activity_days < 30 else 15 if activity_days < 180 else 0
    # many open issues vs stars = unmet needs = room for a better/different version
    gap = min(20, repo["open_issues"] / max(repo["stars"], 1) * 400)
    commercial = 25 if ok else 0
    total = popularity + activity + gap + commercial
    if repo["archived"]:
        total = 0
    # Memory: boost categories that worked before, penalise ones that failed
    cat = memory.get("categories", {}).get(repo["category"], {})
    total += 5 * cat.get("wins", 0) - 5 * cat.get("fails", 0)
    return {
        "score": round(max(0, min(100, total)), 1),
        "license_ok": ok,
        "license_note": license_note,
        "days_since_push": activity_days,
        "differentiation_question": (
            f"Can we build a better/different version of {repo['full_name']} "
            f"with a real reason to use it?"
        ),
    }
