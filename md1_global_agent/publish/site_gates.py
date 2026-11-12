"""Verbatim copy of the security gates in md1god/MDM1.org/scripts/add_app.py (main).

The pre-filter in app_page.check() must agree with the site's final gate, otherwise generated apps are
accepted here and then silently dropped by add-app.yml. KEEP IN SYNC: when the gates change in MDM1.org,
copy the block from "Security gates" down to js_problem() again, unchanged.
"""
import re
from html.parser import HTMLParser

# --- Security gates (allowlist for HTML, hardened blocklist for CSS/JS) ---
ALLOWED_TAGS = {"div", "span", "p", "h2", "h3", "h4", "ul", "ol", "li", "label", "input", "select", "option", "optgroup", "textarea",
                "button", "canvas", "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "br", "hr", "strong", "em", "b", "i",
                "u", "small", "code", "pre", "section", "article", "fieldset", "legend", "output", "details", "summary", "progress",
                "meter", "kbd", "sub", "sup", "mark", "a"}
ALLOWED_ATTRS = {"id", "class", "type", "name", "value", "min", "max", "step", "placeholder", "rows", "cols", "for", "checked", "selected",
                 "disabled", "readonly", "required", "maxlength", "minlength", "width", "height", "role", "title", "dir", "lang", "style",
                 "tabindex", "open", "multiple", "accept", "autocomplete", "inputmode", "pattern", "size", "colspan", "rowspan", "scope",
                 "href", "download", "rel", "low", "high", "optimum"}
BAD_SCHEME = re.compile(r"^(javascript|vbscript|data|blob|file):", re.I)
BAD_STYLE = re.compile(r"url\s*\(|expression\s*\(|@import|\\|behavior|-moz-binding|javascript:|<|/\*", re.I)


class _Allow(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.problem = None

    def _bad(self, why):
        if not self.problem: self.problem = why

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS: return self._bad("tag <%s> is not allowed" % tag)
        for name, val in attrs:
            name = (name or "").lower(); val = val or ""
            if name.startswith("on"): return self._bad("event attribute " + name)
            if not (name in ALLOWED_ATTRS or name.startswith("aria-") or name.startswith("data-")): return self._bad("attribute %s is not allowed" % name)
            flat = re.sub(r"[\s\x00-\x20]+", "", val)
            if BAD_SCHEME.match(flat): return self._bad("dangerous url scheme in " + name)
            if name == "href" and not (tag == "a" and val.startswith("#")): return self._bad("href must be an in-page #anchor on <a>")
            if name == "style" and BAD_STYLE.search(val): return self._bad("unsafe inline style")

    handle_startendtag = handle_starttag

    def handle_comment(self, data): self._bad("html comments are not allowed")
    def handle_decl(self, decl): self._bad("declarations are not allowed")
    def handle_pi(self, data): self._bad("processing instructions are not allowed")
    def unknown_decl(self, data): self._bad("cdata/conditional sections are not allowed")


RAW_DANGEROUS_TAG = re.compile(r"<\s*/?\s*(script|style|iframe|frame|frameset|object|embed|applet|link|meta|base|form|svg|math|template|noscript|img|video|audio|source|track|image|portal|dialog)\b", re.I)


def html_problem(body):
    m = RAW_DANGEROUS_TAG.search(body)
    if m: return "tag <%s> is not allowed" % m.group(1).lower()
    p = _Allow()
    try:
        p.feed(body); p.close()
    except Exception:
        return "html could not be parsed safely"
    return p.problem


def css_problem(css):
    m = BAD_STYLE.search(css)
    return ("unsafe css near '%s'" % m.group(0)[:20]) if m else None


JS_BLOCK = [
    r"\b(fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts|Worker|SharedWorker|BroadcastChannel|RTCPeerConnection|WebTransport|postMessage)\b",
    r"(?-i:\b(eval|Function|Reflect|Proxy|globalThis|__proto__|__defineGetter__|__defineSetter__)\b)",   # case-SENSITIVE: lowercase 'function' is plain JS
    r"\.\s*constructor\b",
    r"\b(localStorage|sessionStorage|indexedDB|openDatabase|cookieStore)\b|\bcaches\s*\.",
    r"\bdocument\s*\.\s*(cookie|domain|write|writeln|location)\b",
    r"\b(window|self|document|this)\s*\[",
    r"\bwindow\s*\.\s*(top|parent|opener|frames|open|name|location|history)\b",
    r"\blocation\b|\bopener\b|\bhistory\s*\.",
    r"\bnavigator\s*\.\s*(sendBeacon|serviceWorker|clipboard|geolocation|mediaDevices|credentials|permissions|share)\b",
    r"\bimport\s*[(.]",
    r"(?<![.\w])open\s*\(",
    r"\b(setTimeout|setInterval)\s*\(\s*[\"'`]",
    r"\bcreateElement\s*\(\s*[\"'`]\s*(script|iframe|frame|object|embed|link|meta|base|form|style)\b",
    r"\bsetAttribute\s*\(\s*[\"'`]\s*(on\w+|src|srcdoc|formaction|action|data)\b",
    r"\.\s*(srcdoc|contentWindow|contentDocument)\b",
    r"[\"'`]\s*(//|https?:|wss?:|ftp:|javascript:|vbscript:|data:text/html)",
    r"https?\s*:\s*/\s*/",
    r"</script|<!--",
]
JS_BLOCK_RE = [re.compile(x, re.I) for x in JS_BLOCK]


def js_problem(js):
    for rx in JS_BLOCK_RE:
        m = rx.search(js)
        if m: return "unsafe js: '%s' is not allowed" % re.sub(r"\s+", " ", m.group(0))[:30]
    return None
