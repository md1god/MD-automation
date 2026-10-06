"""Scout role: finds opportunities on GitHub (first live connector)."""
import os
import requests

API = "https://api.github.com/search/repositories"


def _headers():
    h = {"Accept": "application/vnd.github+json", "User-Agent": "md1-global-agent"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def search(query: str, limit: int = 10):
    """Return a list of normalized repo dicts for a GitHub search query."""
    r = requests.get(
        API,
        params={"q": query, "sort": "stars", "order": "desc", "per_page": limit},
        headers=_headers(),
        timeout=20,
    )
    r.raise_for_status()
    out = []
    for it in r.json().get("items", []):
        lic = (it.get("license") or {}).get("spdx_id") or ""
        out.append(
            {
                "full_name": it["full_name"],
                "url": it["html_url"],
                "description": it.get("description") or "",
                "stars": it.get("stargazers_count", 0),
                "forks": it.get("forks_count", 0),
                "open_issues": it.get("open_issues_count", 0),
                "pushed_at": it.get("pushed_at"),
                "license": lic.lower(),
                "archived": it.get("archived", False),
                "topics": it.get("topics", []),
            }
        )
    return out


def scout(config: dict):
    """Run every configured category query."""
    found = []
    for category, spec in config.get("categories", {}).items():
        try:
            for repo in search(spec["query"], config.get("max_results_per_query", 10)):
                repo["category"] = category
                found.append(repo)
        except Exception as exc:  # network / rate-limit: keep going
            print(f"[scout] {category} failed: {exc}")
    return found
