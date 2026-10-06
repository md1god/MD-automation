"""Decides HOW an opportunity may be used.

modify            -> open-source repo with a commercial-friendly license (keep license notice)
rebuild_original  -> closed software product: only its idea is reusable; new code/design/name
skip              -> no clear license, archived, too big to differentiate, or hardware
"""

HARDWARE_WORDS = (
    "e-ink", "eink", "hardware", "raspberry pi", "arduino", "esp32", "3d print",
    "drone", "robot kit", "sensor", "pcb", "firmware", "wearable", "smart frame",
    "device", "gadget", "kit",
)
MAX_STARS = 30000  # above this the project is too established to differentiate


def _is_hardware(repo: dict) -> bool:
    text = f"{repo.get('full_name','')} {repo.get('description','')}".lower()
    return any(w in text for w in HARDWARE_WORDS)


def mode(repo: dict, analysis: dict) -> str:
    if repo.get("archived"):
        return "skip"
    if repo.get("kind") == "product":
        return "skip" if _is_hardware(repo) else "rebuild_original"
    if repo.get("stars", 0) > MAX_STARS:
        return "skip"
    return "modify" if analysis["license_ok"] else "skip"
