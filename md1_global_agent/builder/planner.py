"""Turn a scored opportunity into a short, license-aware business/build plan.

Providers are tried in config order (free first). Credentials may be supplied directly
as env vars or inside API_KEYS as JSON (for example {"OPENCODE_API_KEY":"...",
"OPENROUTER_API_KEY":"...","GROQ_API_KEY":"..."}) or KEY=value lines. A label that merely
contains the provider name (e.g. "opencode", "OPENCODE_ZEN_KEY") is accepted too.
Secret values are never printed.

A provider may have several models (config list): they are tried one after another, so a
free model that is down or rate-limited does not stop the run.
"""
import json
import os
import requests

PROVIDERS = {
    "opencode": {
        "url": "https://opencode.ai/zen/v1/chat/completions",
        "key_env": "OPENCODE_API_KEY",
        "style": "openai",
    },
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
    "opencode": ["big-pickle", "mimo-v2.5-free", "nemotron-3-ultra-free"],
    "openrouter": ["openrouter/free"],
    "groq": ["llama-3.3-70b-versatile"],
    "github": ["openai/gpt-4o"],
    "anthropic": ["claude-sonnet-4-5"],
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
        if not line or line.startswith("#"):
            continue
        sep = "=" if "=" in line else (":" if ":" in line else None)
        if not sep:
            continue
        key, value = line.split(sep, 1)
        if value.strip():
            out[key.strip().upper()] = value.strip().strip('"').strip("'")
    if out:
        return out
    # Some secret managers store several unnamed tokens separated by whitespace.
    # Infer only well-known prefixes; never send an unrecognized token anywhere.
    for token in raw.replace(",", " ").split():
        token = token.strip().strip('"').strip("'")
        if token.startswith("sk-or-v1-"):
            out["OPENROUTER_API_KEY"] = token
        elif token.startswith("gsk_"):
            out["GROQ_API_KEY"] = token
    return out


def _key_for(provider: str, spec: dict):
    exact = [spec["key_env"], provider.upper(), f"{provider.upper()}_API_KEY"]
    bundle = _bundle_keys()
    for name in exact:
        value = os.getenv(name) or bundle.get(name.upper())
        if value:
            return value
    # Labeled loosely, e.g. OPENCODE_ZEN_KEY -> opencode. Skip the generic GitHub token name.
    if provider != "github":
        for label, value in bundle.items():
            if provider.upper() in label:
                return value
    return None


def _models_for(name: str, llm: dict):
    configured = llm.get("models", {}).get(name, DEFAULT_MODELS[name])
    return [configured] if isinstance(configured, str) else list(configured)


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
    else:
        headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
    body = {"model": model, "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}]}
    resp = requests.post(spec["url"], headers=headers, json=body, timeout=120)
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if spec["style"] == "anthropic":
        text = "".join(b.get("text", "") for b in data["content"])
    else:
        text = data["choices"][0]["message"]["content"] or ""
    if not text.strip():
        raise RuntimeError("empty answer")
    return text


def make_plan(opp: dict, llm: dict = None) -> str:
    """Return the plan text. The provider/model that answered is stored in make_plan.used."""
    llm = llm or {}
    prompt = build_prompt(opp)
    errors = []
    make_plan.used = None
    for name in llm.get("providers", ["opencode", "openrouter", "groq", "github"]):
        spec = PROVIDERS.get(name)
        if not spec:
            errors.append(f"{name}: unsupported provider")
            continue
        key = _key_for(name, spec)
        if not key:
            errors.append(f"{name}: no key")
            continue
        for model in _models_for(name, llm):
            try:
                text = _call(name, model, prompt, key)
                make_plan.used = f"{name}/{model}"
                return text
            except Exception as exc:
                errors.append(f"{name}/{model}: {exc}")
    raise RuntimeError("no LLM provider succeeded -> " + " | ".join(errors))


make_plan.used = None
