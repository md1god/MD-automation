"""Scout role: reads what the research agents found (research/opportunities.json)."""
import json
from pathlib import Path

FILE = Path(__file__).resolve().parents[2] / "research" / "opportunities.json"


def scout(config: dict):
    if not FILE.exists():
        return []
    out = []
    for o in json.loads(FILE.read_text(encoding="utf-8")).get("items", []):
        out.append({
            "kind": "product", "source": "research_agent", "category": o.get("field", "researched"),
            "full_name": o["name"], "url": o["evidence"][0], "description": o.get("summary", ""),
            "stars": 0, "forks": 0, "open_issues": 0, "pushed_at": o.get("found_at"),
            "license": "", "archived": False, "topics": [], "agent_score": o["score"],
            "why_now": o.get("why_now", ""), "evidence": o["evidence"],
            "monetization": o.get("monetization", ""), "how_searched": o.get("how_searched", ""),
        })
    return out
