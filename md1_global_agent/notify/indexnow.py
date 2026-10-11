"""Tell search engines about every new URL right after it is verified live (IndexNow: Bing, Yandex, Seznam, Naver...).
The key file already lives at https://mdm1.org/<key>.txt. Google retired sitemap ping; it finds the URLs through the
sitemaps listed in robots.txt, so the sitemap URLs are submitted too."""
import requests

KEY = "14aaa353c0894bc3f8a8e7855831190e"
HOST = "mdm1.org"
SITEMAPS = [f"https://{HOST}/sitemap.xml", f"https://{HOST}/sitemap-tools.xml", f"https://{HOST}/sitemap-apps.xml",
            f"https://{HOST}/tools/", f"https://{HOST}/apps/"]


def submit(urls) -> bool:
    urls = [u for u in dict.fromkeys(list(urls) + SITEMAPS) if u.startswith(f"https://{HOST}/")]
    body = {"host": HOST, "key": KEY, "keyLocation": f"https://{HOST}/{KEY}.txt", "urlList": urls}
    ok = False
    for ep in ("https://api.indexnow.org/indexnow", "https://www.bing.com/indexnow"):
        try:
            r = requests.post(ep, json=body, timeout=30)
            print(f"IndexNow {ep.split('/')[2]}: {r.status_code}")
            ok = ok or r.status_code in (200, 202)
        except Exception as exc:
            print(f"IndexNow error {type(exc).__name__}")
    return ok


def hashtags(title: str, base=("MDM1",), extra=()) -> str:
    """Arabic/English hashtags from the title's own words (no invented trends)."""
    import re
    words = [w for w in re.findall(r"[\w]{3,}", title) if not w.isdigit()][:4]
    tags = list(base) + list(extra) + ["_".join([w]) for w in words]
    return " ".join("#" + t for t in dict.fromkeys(tags))
