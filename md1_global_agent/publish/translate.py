"""Translates the (already sanitized) Arabic plan into the site's languages with the free LLM chain.

Output format is plain markers (TITLE/DESCRIPTION/BODY), not JSON: free models break JSON often.
A language that fails any gate is simply skipped - the page still publishes with the others.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor

import privacy
from builder.planner import complete

LANG_NAMES = {
    "en": "English", "es": "Spanish", "pt": "Brazilian Portuguese", "id": "Indonesian",
    "tr": "Turkish", "fr": "French", "de": "German", "hi": "Hindi", "ru": "Russian",
}
SRC_LIMIT = 5500          # characters of Arabic body sent for translation
OUT_LIMIT = 4500          # characters kept per translated body
TOTAL_LIMIT = 45000       # workflow_dispatch inputs are capped at 65k characters in total

_PARSE = re.compile(r"TITLE\s*:\s*(?P<t>.+?)\n+\s*DESCRIPTION\s*:\s*(?P<d>.+?)\n+\s*BODY\s*:\s*\n?(?P<b>.+)",
                    re.S | re.I)


def _prompt(lang_name: str, title: str, description: str, body: str) -> str:
    return (
        f"Translate the following Arabic project plan into {lang_name}. Keep the meaning, keep bullets "
        "and paragraph breaks, keep technology names as they are. Do NOT add commentary, do NOT add any "
        "URL, and do NOT invent a project/source name. Reply in EXACTLY this format and nothing else:\n"
        "TITLE: <translated title>\nDESCRIPTION: <translated description, max 150 characters>\n"
        f"BODY:\n<translated body, plain text, at most {OUT_LIMIT} characters>\n\n"
        f"TITLE: {title}\nDESCRIPTION: {description}\nBODY:\n{body}"
    )


def parse(text: str):
    text = re.sub(r"^```\w*\s*|\s*```\s*$", "", (text or "").strip())
    m = _PARSE.search(text)
    if not m:
        return None
    clean = lambda v: re.sub(r"[*_`#]+", "", v).strip()
    return {"title": clean(m.group("t"))[:160], "description": clean(m.group("d"))[:200],
            "body": m.group("b").strip()[:OUT_LIMIT]}


def _arabic_ratio(text: str) -> float:
    letters = re.findall(r"[^\W\d_]", text)
    return len(re.findall(r"[؀-ۿ]", text)) / len(letters) if letters else 0.0


def gate(item: dict, source_body: str, terms: list):
    whole = "\n".join((item["title"], item["description"], item["body"]))
    if len(item["body"]) < 0.3 * min(len(source_body), OUT_LIMIT) or not item["title"]:
        return False, "too short"
    if _arabic_ratio(whole) > 0.3:
        return False, "not translated"
    if re.search(r"<\s*script|javascript:", whole, re.I):
        return False, "unsafe markup"
    if privacy.leaks(whole, terms):
        return False, "source identity leaked"
    return True, ""


def _cut_paragraphs(body: str, limit: int) -> str:
    if len(body) <= limit:
        return body
    cut = body[:limit]
    return cut[:cut.rfind("\n")] if "\n" in cut else cut


def translate_all(payload: dict, terms: list, llm: dict, languages, budget: int = 900, workers: int = 3):
    """Return {code: {title, description, body}} for the languages that passed every gate."""
    source = _cut_paragraphs(payload["body"], SRC_LIMIT)
    deadline = time.time() + budget
    wanted = [c for c in languages if c in LANG_NAMES]

    def one(code):
        try:
            raw = complete(_prompt(LANG_NAMES[code], payload["title"], payload["description"], source),
                           llm, deadline=deadline)
        except Exception as exc:
            return code, None, f"llm: {str(exc)[:120]}"
        item = parse(raw)
        if not item:
            return code, None, "unparseable answer"
        ok, why = gate(item, source, terms)
        return code, (item if ok else None), why

    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for code, item, why in pool.map(one, wanted):
            print(f"Translate {code}: {'ok' if item else 'skipped (' + why + ')'}")
            if item:
                results[code] = item
    # keep the dispatch payload under the platform limit
    while results and sum(len(i["body"]) + len(i["title"]) + len(i["description"]) for i in results.values()) > TOTAL_LIMIT:
        results.pop(list(results)[-1])
    return results
