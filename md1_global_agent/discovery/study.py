"""Study an opportunity before building from it (idea-level 'reverse engineering').

Reads the public README and the top-level file layout of an open-source repository so the idea-maker knows the REAL
features and workflow of the product instead of guessing from a one-line description. Only understanding is used:
no code, text, names or assets are copied (the privacy leak-check still guards the result).
"""
import base64
import os
import re

import requests

API = "https://api.github.com/repos/"


def _h():
    h = {"Accept": "application/vnd.github+json", "User-Agent": "md1-global-agent"}
    if os.getenv("GITHUB_TOKEN"):
        h["Authorization"] = f"Bearer {os.getenv('GITHUB_TOKEN')}"
    return h


def study(repo: dict, limit: int = 3500) -> str:
    name = repo.get("full_name", "")
    if "/" not in name or repo.get("kind") == "product":
        return ""
    out = []
    try:
        r = requests.get(f"{API}{name}/readme", headers=_h(), timeout=20)
        if r.ok:
            txt = base64.b64decode(r.json().get("content", "")).decode("utf-8", "ignore")
            txt = re.sub(r"!?\[[^\]]*\]\([^)]*\)|<[^>]+>|```.*?```", " ", txt, flags=re.S)
            out.append("README (features/usage): " + re.sub(r"\s+", " ", txt)[:limit])
    except Exception:
        pass
    try:
        r = requests.get(f"{API}{name}/contents", headers=_h(), timeout=20)
        if r.ok and isinstance(r.json(), list):
            out.append("Top-level layout: " + ", ".join(i["name"] for i in r.json()[:40]))
    except Exception:
        pass
    if repo.get("topics"):
        out.append("Topics: " + ", ".join(repo["topics"][:15]))
    return "\n".join(out)
