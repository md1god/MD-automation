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
    is_product = repo.get("kind") == "product"
    if "agent_score" in repo:      # researched by an agent with cited evidence: its verified score is used
        return {"score": round(float(repo["agent_score"]), 1), "license_ok": True,
                "license_note": "idea only: rebuilt original (no code/design/name reuse)",
                "days_since_push": 0, "differentiation_question": repo.get("why_now", "")}
    idea_only = bool(config.get("idea_only"))
    if idea_only:
        ok, license_note = True, "idea only: rebuilt original (no code/design/name reuse)"
    elif is_product:
        # Closed product: only the idea is reusable, so no license is needed.
        ok, license_note = True, "closed product: rebuild original (no code/design/name reuse)"
    else:
        ok, license_note = license_check(repo, config.get("allowed_licenses", []))
    # Audience proof, peaking for mid-size projects (~300-8000 stars); giants have no room.
    logs = math.log10(max(repo["stars"], 1))
    popularity = min(30, logs * 8) if logs <= 3.9 else max(5, 30 - (logs - 3.9) * 20)
    activity_days = _days_since(repo["pushed_at"])
    activity = 25 if activity_days < 30 else 15 if activity_days < 180 else 0
    # repos: many open issues vs stars = unmet needs; products: heavy discussion = demand
    ratio = repo["open_issues"] / max(repo["stars"], 1)
    gap = min(20, ratio * (60 if is_product else 400))
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
