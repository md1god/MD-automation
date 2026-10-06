"""License / commercial-use gate. Dependencies' licenses still need a separate audit."""


def check(repo: dict, allowed: list):
    spdx = (repo.get("license") or "").lower()
    if not spdx or spdx in ("noassertion", "other"):
        return False, "no clear license — do not reuse"
    if spdx in allowed:
        return True, f"{spdx} allows commercial use"
    return False, f"{spdx} not in allowed list (review manually)"
