"""Decides HOW an opportunity may be used.

modify            -> open-source repo with a commercial-friendly license (keep license notice)
rebuild_original  -> closed product: only its idea is reusable; build with new code/design/name
skip              -> repo without a clear license, or archived: do not reuse
"""


def mode(repo: dict, analysis: dict) -> str:
    if repo.get("archived"):
        return "skip"
    if repo.get("kind") == "product":
        return "rebuild_original"
    return "modify" if analysis["license_ok"] else "skip"
