"""Builder step 1: turns an opportunity into a concrete business + build plan using Claude.

Needs the ANTHROPIC_API_KEY environment variable (a GitHub Actions secret).
Planning only: it reads nothing private and publishes nothing.
"""
import os
import requests

API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5-5"

PROMPTS = {
    "modify": (
        "This is an open-source project with a commercial-friendly license. Plan how to "
        "modify it into a differentiated paid product. Keep the license and copyright notice."
    ),
    "rebuild_original": (
        "This is a closed trending product. Only its IDEA may be reused. Plan an ORIGINAL "
        "product that solves the same problem better: new name, new brand, new design, all "
        "code written from scratch. Copy nothing from it."
    ),
}


def make_plan(opp: dict, api_key: str = None) -> str:
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    r, a = opp["repo"], opp["analysis"]
    prompt = (
        f"{PROMPTS[opp['mode']]}\n\n"
        f"Opportunity: {r['full_name']}\nURL: {r['url']}\nCategory: {r['category']}\n"
        f"Description: {r['description']}\nPopularity: {r['stars']} | Score: {a['score']}\n\n"
        "Answer in Markdown with these sections: 1) Target audience 2) Differentiation "
        "(why choose ours) 3) MVP scope (max 8 tasks) 4) Pricing and revenue model "
        "5) Distribution plan 6) Risks (legal, technical) 7) Suggested name and one-line pitch. "
        "Be concrete and short."
    )
    resp = requests.post(
        API,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 2000,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    resp.raise_for_status()
    return "".join(b.get("text", "") for b in resp.json()["content"])
