"""Turn a scored opportunity into a short, license-aware business/build plan.

Providers are tried in config order (free first). Credentials come from env vars (one
secret per provider) or, optionally, from an API_KEYS bundle (JSON or KEY=value lines).
Secret values are never printed.

Why these providers behave as they do (learned from real runs):
  opencode_cli  OpenCode's free models are refused over the API ("free tier can only be used
                from within OpenCode"), so we run the real `opencode` CLI instead.
  openrouter    the `openrouter/free` router can answer with an empty body, and fixed model
                names go stale, so free models are discovered from /models at run time.
  groq          model names are deprecated often; the models the key can use are listed first.
  github        GitHub Models; non-JSON answers are reported readably.
Each provider tries several models, so one dead model never stops the run.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import requests

PROVIDERS = {
    "opencode_cli": {"style": "cli", "key_env": ""},
    "opencode": {
        "url": "https://opencode.ai/zen/v1/chat/completions",
        "key_env": "OPENCODE_API_KEY",
        "style": "openai",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "models_url": "https://openrouter.ai/api/v1/models",
        "key_env": "OPENROUTER_API_KEY",
        "style": "openai",
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "models_url": "https://api.groq.com/openai/v1/models",
        "key_env": "GROQ_API_KEY",
        "style": "openai",
    },
    "github": {
        "url": "https://models.github.ai/inference/chat/completions",
        "key_env": "GITHUB_TOKEN",
        "style": "openai",
        "extra_headers": {"Accept": "application/vnd.github+json",
                          "X-GitHub-Api-Version": "2022-11-28"},
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1/messages",
        "key_env": "ANTHROPIC_API_KEY",
        "style": "anthropic",
    },
}

DEFAULT_MODELS = {
    "opencode_cli": ["big-pickle", "mimo-v2.6-flash-free", "nemotron-3-ultra-free"],
    "opencode": ["big-pickle"],
    "openrouter": [],
    "groq": [],
    "github": ["openai/gpt-4o"],
    "anthropic": ["claude-sonnet-4-5"],
}

MAX_DISCOVERED = 4
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

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
    """Optional API_KEYS bundle; tolerate JSON and KEY=value formats."""
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
    for token in raw.replace(",", " ").split():
        token = token.strip().strip('"').strip("'")
        if token.startswith("sk-or-v1-"):
            out["OPENROUTER_API_KEY"] = token
        elif token.startswith("gsk_"):
            out["GROQ_API_KEY"] = token
    return out


def _key_for(provider: str, spec: dict):
    if not spec.get("key_env"):
        return None
    exact = [spec["key_env"], provider.upper(), f"{provider.upper()}_API_KEY"]
    bundle = _bundle_keys()
    for name in exact:
        value = os.getenv(name) or bundle.get(name.upper())
        if value:
            return value.strip()
    if provider != "github":
        for label, value in bundle.items():
            if provider.upper() in label:
                return value.strip()
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


# ---------------------------------------------------------------- model discovery

def _size_hint(model_id: str) -> int:
    nums = [int(n) for n in re.findall(r"(\d+)b", model_id.lower())]
    return max(nums) if nums else 0


def discover_openrouter(key: str, spec: dict):
    """Free text models, biggest context first. The /models list is public."""
    resp = requests.get(spec["models_url"], timeout=30)
    resp.raise_for_status()
    free = []
    for m in resp.json().get("data", []):
        price = m.get("pricing") or {}
        if str(price.get("prompt")) != "0" or str(price.get("completion")) != "0":
            continue
        outs = (m.get("architecture") or {}).get("output_modalities") or ["text"]
        if outs != ["text"]:
            continue
        free.append((m.get("context_length") or 0, m["id"]))
    free.sort(reverse=True)
    return [mid for _, mid in free]


def discover_groq(key: str, spec: dict):
    """Chat models this key can use, largest first."""
    resp = requests.get(spec["models_url"], headers={"Authorization": f"Bearer {key}"}, timeout=30)
    resp.raise_for_status()
    skip = ("whisper", "tts", "guard", "playai", "orpheus", "embed", "distil")
    ids = [m["id"] for m in resp.json().get("data", [])
           if m.get("active", True) and not any(w in m["id"].lower() for w in skip)]
    ids.sort(key=lambda i: (_size_hint(i), "gpt-oss" in i), reverse=True)
    return ids


def discover_opencode_cli():
    """Free models the installed CLI knows about (`opencode models opencode`)."""
    out = subprocess.run(["opencode", "models", "opencode"], capture_output=True, text=True,
                         timeout=60, cwd=tempfile.gettempdir())
    names = [ANSI.sub("", ln).strip().split("/")[-1] for ln in out.stdout.splitlines()]
    return [n for n in names if n == "big-pickle" or n.endswith("-free")]


DISCOVER = {"openrouter": discover_openrouter, "groq": discover_groq}


def _models_for(name: str, llm: dict, key):
    configured = llm.get("models", {}).get(name, DEFAULT_MODELS[name])
    configured = [configured] if isinstance(configured, str) else list(configured)
    found = []
    try:
        if name in DISCOVER:
            found = DISCOVER[name](key, PROVIDERS[name])
        elif name == "opencode_cli" and shutil.which("opencode"):
            found = discover_opencode_cli()
    except Exception:
        found = []
    if found and name in ("groq", "opencode_cli"):
        configured = [m for m in configured if m in found]   # drop deprecated names
    order = []
    for m in configured + found[:MAX_DISCOVERED]:
        if m not in order:
            order.append(m)
    return order


# ---------------------------------------------------------------- calls

def _call_cli(model: str, prompt: str) -> str:
    if not shutil.which("opencode"):
        raise RuntimeError("opencode CLI not installed (npm i -g opencode-ai)")
    with tempfile.TemporaryDirectory() as empty:        # no repo files for the agent to touch
        done = subprocess.run(
            ["opencode", "run", "--model", f"opencode/{model}", prompt],
            capture_output=True, text=True, timeout=240, cwd=empty)
    text = ANSI.sub("", done.stdout or "")
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("> ")]
    text = "\n".join(lines).strip()
    if done.returncode != 0 or not text:
        err = ANSI.sub("", (done.stderr or done.stdout or "")).strip()[:300]
        raise RuntimeError(f"cli exit {done.returncode}: {err or 'empty answer'}")
    return text


def _call_http(name: str, model: str, prompt: str, key: str) -> str:
    spec = PROVIDERS[name]
    if spec["style"] == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
    else:
        headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
    headers.update(spec.get("extra_headers", {}))
    body = {"model": model, "max_tokens": 4000,
            "messages": [{"role": "user", "content": prompt}]}
    resp = requests.post(spec["url"], headers=headers, json=body, timeout=180)
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code}: {resp.text[:300]}")
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"non-JSON answer (HTTP {resp.status_code}): {resp.text[:120]!r}")
    if spec["style"] == "anthropic":
        text = "".join(b.get("text", "") for b in data.get("content", []))
    else:
        text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not text.strip():
        raise RuntimeError("empty answer")
    return text


def make_plan(opp: dict, llm: dict = None) -> str:
    """Return the plan text. The provider/model that answered is stored in make_plan.used."""
    llm = llm or {}
    prompt = build_prompt(opp)
    errors = []
    make_plan.used = None
    for name in llm.get("providers", ["opencode_cli", "openrouter", "groq", "github"]):
        spec = PROVIDERS.get(name)
        if not spec:
            errors.append(f"{name}: unsupported provider")
            continue
        key = _key_for(name, spec)
        if spec["style"] != "cli" and not key:
            errors.append(f"{name}: no key")
            continue
        models = _models_for(name, llm, key)
        if not models:
            errors.append(f"{name}: no usable model")
            continue
        for model in models:
            try:
                text = (_call_cli(model, prompt) if spec["style"] == "cli"
                        else _call_http(name, model, prompt, key))
                make_plan.used = f"{name}/{model}"
                return text
            except Exception as exc:
                errors.append(f"{name}/{model}: {str(exc)[:200]}")
    raise RuntimeError("no LLM provider succeeded -> " + " | ".join(errors))


make_plan.used = None
