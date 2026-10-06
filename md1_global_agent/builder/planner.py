"""Builder step 1: turns an opportunity into a concrete business + build plan using an LLM.

Providers are tried in the order given by config `llm.providers`; the first one that has
credentials AND answers successfully wins:
  github     FREE. Uses the workflow's built-in GITHUB_TOKEN (needs `models: read`).
  groq       free tier. Needs GROQ_API_KEY.
  anthropic  paid. Needs ANTHROPIC_API_KEY.
Planning only: it publishes nothing.
"""
import os
import requests

PROVIDERS = {
    "github": {
        "url": "https://models.github.ai/inference/chat/completions",
        "key_env": "GITHUB_TOKEN",
        "style": "openai",
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key_env": "GROQ_API_KEY",
        "style": "openai",
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1/messages",
        "key_env": "ANTHROPIC_API_KEY",
        "style": "anthropic",
    },
}

DEFAULT_MODELS = {
    "github": "openai/gpt-4o",
    "groq": "llama-3.3-70b-versatile",
    "anthropic": "claude-sonnet-5-5",
}

PROMPTS = {
    "modify": (
        "This is an open-source project with a commercial-friendly license. Plan how to "
        "modify it into a differentiated product. Keep the license and copyright notice. "
        "Prefer a free-to-start model (free tier first, monetize later)."
    ),
    "rebuild_original": (
        "This is a closed trending product. Only its IDEA may be reused. Plan an ORIGINAL "
        "product that solves the same problem better: new name, new brand, new design, all "
        "code written from scratch. Copy nothing from it. Prefer a free-to-start model."
    ),
}


def build_prompt(opp: dict) -> str:
    r, a = opp["repo"], opp["analysis"]
    return (
        f"{PROMPTS[opp['mode']]}\n\n"
        f"Opportunity: {r['full_name']}\nURL: {r['url']}\nCategory: {r['category']}\n"
        f"Description: {r['description']}\nPopularity: {r['stars']} | Score: {a['score']}\n\n"
        "Answer in Markdown with these sections: 1) Target audience 2) Differentiation "
        "(why choose ours) 3) MVP scope (max 8 tasks) 4) Pricing and revenue model "
        "5) Global distribution plan using free channels 6) Risks (legal, technical) "
        "7) Suggested name and one-line pitch. Be concrete and short."
    )


def _call(name: str, model: str, prompt: str, key: str) -> str:
    spec = PROVIDERS[name]
    if spec["style"] == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        body = {"model": model, "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}]}
    else:
        headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
        body = {"model": model, "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}]}
    resp = requests.post(spec["url"], headers=headers, json=body, timeout=120)
    if not resp.ok:
        # Show the provider's own error text (never contains our key) to make failures debuggable.
        raise RuntimeError(f"{resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if spec["style"] == "anthropic":
        return "".join(b.get("text", "") for b in data["content"])
    return data["choices"][0]["message"]["content"]


def make_plan(opp: dict, llm: dict = None) -> str:
    llm = llm or {}
    prompt = build_prompt(opp)
    errors = []
    for name in llm.get("providers", ["github", "groq", "anthropic"]):
        spec = PROVIDERS.get(name)
        key = os.getenv(spec["key_env"]) if spec else None
        if not key:
            continue
        model = llm.get("models", {}).get(name, DEFAULT_MODELS[name])
        try:
            return _call(name, model, prompt, key)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise RuntimeError("no LLM provider succeeded -> " + " | ".join(errors) if errors
                       else "no LLM credentials available")
