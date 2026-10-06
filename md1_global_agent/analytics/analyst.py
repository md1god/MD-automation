"""Analyst role: summarizes a run and suggests strategy adjustments."""
from collections import Counter


def summarize(opportunities: list):
    cats = Counter(o["repo"]["category"] for o in opportunities if o["analysis"]["score"] >= 60)
    best = max(cats, key=cats.get) if cats else None
    return {
        "total": len(opportunities),
        "qualified_by_category": dict(cats),
        "advice": f"Focus next search on '{best}'." if best else "Widen search queries.",
    }
