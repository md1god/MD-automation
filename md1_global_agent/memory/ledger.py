"""Persistent anti-repeat ledger (two levels), safe to commit to a PUBLIC repository.

Level 1 - examined : an opportunity already shown in a report or planned is never surfaced again.
Level 2 - published: a page already published for an opportunity is never sent again.

Only keyed hashes (HMAC-SHA256) are stored - never project names or URLs - so the file does not
reveal which projects the scout looked at. Set the optional LEDGER_SALT secret once and never change
it afterwards (changing it makes old entries unrecognisable, i.e. de-duplication starts over).
"""
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

LEDGER_FILE = Path(__file__).resolve().parent / "ledger.json"
_DEFAULT_PEPPER = "md1-ledger-v1"


def _norm(identity: str) -> str:
    return re.sub(r"\s+", " ", (identity or "").strip().lower())


def key_for(identity: str) -> str:
    """Stable keyed hash of an opportunity identity (full name / product title)."""
    salt = os.getenv("LEDGER_SALT", "").strip() or _DEFAULT_PEPPER
    return hmac.new(salt.encode("utf-8"), _norm(identity).encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def public_id(identity: str) -> str:
    """Short opaque id that is safe to show in Telegram, logs and public pages."""
    return key_for(identity)[:10]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    def __init__(self, path=LEDGER_FILE):
        self.path = Path(path)
        self.data = {"version": 1, "examined": {}, "published": {}}
        if self.path.exists():
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            for section in ("examined", "published"):
                self.data[section].update(loaded.get(section, {}))

    # ---- queries
    def is_examined(self, identity: str) -> bool:
        return key_for(identity) in self.data["examined"]

    def is_published(self, identity: str) -> bool:
        return key_for(identity) in self.data["published"]

    def is_known(self, identity: str) -> bool:
        """True if the opportunity must not be surfaced again (either level)."""
        return self.is_examined(identity) or self.is_published(identity)

    # ---- updates
    def mark_examined(self, identity: str, how: str = "shown") -> None:
        self.data["examined"].setdefault(key_for(identity), {"at": _now(), "how": how})

    def mark_published(self, identity: str, url: str) -> None:
        self.mark_published_key(key_for(identity), url)

    def mark_published_key(self, key: str, url: str) -> None:
        self.data["published"][key] = {"at": _now(), "url": url}
        self.data["examined"].setdefault(key, {"at": _now(), "how": "published"})

    def import_legacy_names(self, names) -> int:
        """One-time migration of plain names (old memory/planned.json) into hashed entries."""
        before = len(self.data["examined"])
        for name in names:
            self.mark_examined(name, "legacy")
        return len(self.data["examined"]) - before

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)
