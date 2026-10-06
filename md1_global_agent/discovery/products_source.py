"""Scout role: trending *products* (mostly closed-source) from Hacker News and Product Hunt.

These are idea sources only. We never copy their code, design, name or content.
"""
import os
import requests

HN_API = "https://hn.algolia.com/api/v1/search"
PH_API = "https://api.producthunt.com/v2/api/graphql"


def hacker_news(limit: int = 20):
    """Top 'Show HN' posts (no API key needed)."""
    r = requests.get(
        HN_API,
        params={"tags": "show_hn", "hitsPerPage": limit,
                "numericFilters": "points>50"},
        headers={"User-Agent": "md1-global-agent"},
        timeout=20,
    )
    r.raise_for_status()
    out = []
    for h in r.json().get("hits", []):
        out.append({
            "kind": "product",
            "source": "hackernews",
            "full_name": h.get("title", "")[:120],
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            "description": h.get("title", ""),
            "stars": h.get("points", 0),
            "forks": 0,
            "open_issues": h.get("num_comments", 0),
            "pushed_at": h.get("created_at"),
            "license": "",
            "archived": False,
            "topics": [],
            "category": "trending_products",
        })
    return out


def product_hunt(limit: int = 20):
    """Top Product Hunt posts. Optional: needs PRODUCTHUNT_TOKEN, skipped otherwise."""
    token = os.getenv("PRODUCTHUNT_TOKEN")
    if not token:
        return []
    query = ("{ posts(first: %d, order: VOTES) { edges { node { name tagline url "
             "votesCount commentsCount createdAt } } } }" % limit)
    r = requests.post(PH_API, json={"query": query},
                      headers={"Authorization": f"Bearer {token}"}, timeout=20)
    r.raise_for_status()
    out = []
    for e in r.json()["data"]["posts"]["edges"]:
        n = e["node"]
        out.append({
            "kind": "product",
            "source": "producthunt",
            "full_name": n["name"],
            "url": n["url"],
            "description": n["tagline"],
            "stars": n["votesCount"],
            "forks": 0,
            "open_issues": n["commentsCount"],
            "pushed_at": n["createdAt"],
            "license": "",
            "archived": False,
            "topics": [],
            "category": "trending_products",
        })
    return out


def scout(config: dict):
    found = []
    n = config.get("max_results_per_query", 10) * 2
    for name, fn in (("hackernews", hacker_news), ("producthunt", product_hunt)):
        if name not in config.get("product_sources", []):
            continue
        try:
            found.extend(fn(n))
        except Exception as exc:
            print(f"[scout] {name} failed: {exc}")
    return found
