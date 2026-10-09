"""Scout role: finds opportunities on GitHub (first live connector)."""
import os
import time
import requests

API = "https://api.github.com/search/repositories"


def _headers():
    h = {"Accept": "application/vnd.github+json", "User-Agent": "md1-global-agent"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def search(query: str, limit: int = 10, page: int = 1):
    """Return a list of normalized repo dicts for a GitHub search query."""
    r = requests.get(
        API,
        params={"q": query, "sort": "stars", "order": "desc", "per_page": limit, "page": page},
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


def scout(config: dict, is_known=None):
    """Run every configured category query.

    `is_known(full_name)` skips opportunities that were already examined/published; the search keeps
    paging (up to `max_pages`) until it has `max_results_per_query` NEW ones, so every day digs deeper
    instead of returning the same top results.
    """
    found = []
    limit = config.get("max_results_per_query", 10)
    max_pages = config.get("max_pages", 4)
    for category, spec in config.get("categories", {}).items():
        fresh = []
        try:
            for page in range(1, max_pages + 1):
                batch = search(spec["query"], limit, page)
                fresh += [r for r in batch if not (is_known and is_known(r["full_name"]))]
                if len(fresh) >= limit or len(batch) < limit:
                    break
                time.sleep(2)
        except Exception as exc:  # network / rate-limit: keep going
            print(f"[scout] {category} failed: {exc}")
        for repo in fresh[:limit]:
            repo["category"] = category
            found.append(repo)
    return found
