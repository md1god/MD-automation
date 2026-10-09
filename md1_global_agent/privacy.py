"""Keeps the identity of the source project out of everything that can become public.

This repository is public: workflow logs, job summaries and artifacts are readable by anyone.
Names/URLs of source projects are therefore removed before anything is printed, written to a
report or published.
"""
import re
from urllib.parse import urlparse

HIDDEN = "[مصدر مخفي]"
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)

# Too generic to hide on their own (they would damage normal sentences).
GENERIC = {
    "tool", "tools", "app", "apps", "api", "apis", "saas", "agent", "agents", "data", "platform",
    "open", "source", "cli", "web", "free", "pro", "kit", "hub", "lab", "labs", "core", "server",
    "client", "cloud", "online", "ai", "show", "hn",
}
AGGREGATOR_HOSTS = {"github.com", "news.ycombinator.com", "producthunt.com", "www.producthunt.com",
                    "reddit.com", "www.reddit.com", "gitlab.com"}


def _product_name(full_name: str) -> str:
    """'Show HN: Foo - bar baz' -> 'Foo'."""
    name = re.sub(r"^\s*(show|ask|launch)\s+hn\s*[:\-]\s*", "", full_name or "", flags=re.I)
    return re.split(r"\s+[-–—|:]\s+|:\s", name, maxsplit=1)[0].strip()


def identity_terms(repo: dict) -> list:
    """Every string that would reveal the source of this opportunity (longest first)."""
    full = (repo.get("full_name") or "").strip()
    terms = {full}
    if "/" in full and not full.startswith("http"):
        owner, base = full.split("/", 1)
        terms.update({owner, base, base.replace("-", " "), base.replace("-", "")})
    else:
        terms.add(_product_name(full))
    host = urlparse(repo.get("url") or "").netloc.lower()
    if host and host not in AGGREGATOR_HOSTS:
        terms.update({host, host.removeprefix("www.")})
    clean = [t.strip() for t in terms if len(t.strip()) >= 3 and t.strip().lower() not in GENERIC]
    return sorted(set(clean), key=len, reverse=True)


def _pattern(term: str):
    return re.compile(r"(?<![\w])" + re.escape(term) + r"(?![\w])", re.I)


def sanitize(text: str, terms: list) -> str:
    """Remove URLs and replace every identity term."""
    text = URL_RE.sub("", text or "")
    for t in terms:
        text = _pattern(t).sub(HIDDEN, text)
    return text


def leaks(text: str, terms: list) -> list:
    """Identity terms (or any URL) still present in `text`; empty list = clean."""
    found = [t for t in terms if _pattern(t).search(text or "")]
    if URL_RE.search(text or ""):
        found.append("<url>")
    return found
