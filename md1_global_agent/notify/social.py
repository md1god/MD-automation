"""Optional free promotion on the owner's OWN accounts (never mass-posting, never other people's spaces).

One honest post per published tool/app, with the link. Each network is used only if its secrets exist:
  Bluesky : BSKY_HANDLE + BSKY_APP_PASSWORD   (Settings -> App passwords)
  Mastodon: MASTODON_BASE_URL (e.g. https://mastodon.social) + MASTODON_ACCESS_TOKEN (scope write:statuses)
Returns the list of networks that accepted the post.
"""
import os
from datetime import datetime, timezone

import requests


def _bluesky(text: str, url: str) -> bool:
    handle, password = os.getenv("BSKY_HANDLE", "").strip(), os.getenv("BSKY_APP_PASSWORD", "").strip()
    if not handle or not password:
        return False
    s = requests.post("https://bsky.social/xrpc/com.atproto.server.createSession",
                      json={"identifier": handle, "password": password}, timeout=30)
    if not s.ok:
        print(f"Social: bluesky login failed ({s.status_code})")
        return False
    sess = s.json()
    body = f"{text}\n{url}"
    start = len(body[: body.rindex(url)].encode("utf-8"))
    record = {"$type": "app.bsky.feed.post", "text": body, "langs": ["ar"],
              "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "facets": [{"index": {"byteStart": start, "byteEnd": start + len(url.encode("utf-8"))},
                          "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}]}]}
    r = requests.post("https://bsky.social/xrpc/com.atproto.repo.createRecord",
                      headers={"Authorization": f"Bearer {sess['accessJwt']}"}, timeout=30,
                      json={"repo": sess["did"], "collection": "app.bsky.feed.post", "record": record})
    print(f"Social: bluesky {'ok' if r.ok else 'failed ' + str(r.status_code)}")
    return r.ok


def _mastodon(text: str, url: str) -> bool:
    base, token = os.getenv("MASTODON_BASE_URL", "").strip().rstrip("/"), os.getenv("MASTODON_ACCESS_TOKEN", "").strip()
    if not base or not token:
        return False
    r = requests.post(f"{base}/api/v1/statuses", headers={"Authorization": f"Bearer {token}"}, timeout=30,
                      data={"status": f"{text}\n{url}", "language": "ar", "visibility": "public"})
    print(f"Social: mastodon {'ok' if r.ok else 'failed ' + str(r.status_code)}")
    return r.ok


def announce(text: str, url: str) -> list:
    done = []
    for name, fn in (("bluesky", _bluesky), ("mastodon", _mastodon)):
        try:
            if fn(text[:240], url):
                done.append(name)
        except Exception as exc:                       # promotion must never break the run
            print(f"Social: {name} error {type(exc).__name__}")
    return done
