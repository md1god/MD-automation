"""Turn a scored opportunity into a short, license-aware business/build plan.

Providers are tried in config order. Credentials may be supplied directly or inside
API_KEYS as JSON (for example {"OPENROUTER_API_KEY":"...","GROQ_API_KEY":"..."})
or KEY=value lines. Secret values are never printed.
"""
import json
import os
import requests

PROVIDERS = {
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key_env": "OPENROUTER_API_KEY",
        "style": "openai",
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key_env": "GROQ_API_KEY",
        "style": "openai",
    },
    "github": {
        "url": "https://models.github.ai/inference/chat/completions",
        "key_env": "GITHUB_TOKEN",
        "style": "openai",
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1/messages",
        "key_env": "ANTHROPIC_API_KEY",
        "style": "anthropic",
    },
}

DEFAULT_MODELS = {
    "openrouter": "openrouter/free",
    "groq": "llama-3.3-70b-versatile",
    "github": "openai/gpt-4o",
    "anthropic": "claude-sonnet-4-5",
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


def _bundle_keys():
    """Read API_KEYS without ever logging it; tolerate JSON and KEY=value formats."""
    raw = os.getenv("API_KEYS", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k).upper(): str(v) for k, v in data.items() if v}
    except (json.JSONDecodeError, TypeError):
        pass
    out = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if value.strip():
            out[key.strip().upper()] = value.strip().strip('"').strip("'")
    return out


def _key_for(provider: str, spec: dict):
    aliases = [spec["key_env"], provider.upper(), f"{provider.upper()}_API_KEY"]
    bundle = _bundle_keys()
    for name in aliases:
        value = os.getenv(name) or bundle.get(name.upper())
        if value:
            return value
    return None


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
        raise RuntimeError(f"{resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if spec["style"] == "anthropic":
        return "".join(b.get("text", "") for b in data["content"])
    return data["choices"][0]["message"]["content"]


def make_plan(opp: dict, llm: dict = None) -> str:
    llm = llm or {}
    prompt = build_prompt(opp)
    errors = []
    for name in llm.get("providers", ["openrouter", "groq", "github"]):
        spec = PROVIDERS.get(name)
        if not spec:
            errors.append(f"{name}: unsupported provider")
            continue
        key = _key_for(name, spec)
        if not key:
            continue
        model = llm.get("models", {}).get(name, DEFAULT_MODELS[name])
        try:
            return _call(name, model, prompt, key)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise RuntimeError("no LLM provider succeeded -> " + " | ".join(errors)
                       if errors else "no LLM credentials available")
