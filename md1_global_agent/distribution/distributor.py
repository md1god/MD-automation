"""Distributor role: prepares platform-specific drafts. Never posts anything yet.

Traffic goes to the owner's own sites (config: destinations).
"""

PLATFORMS = ["x", "reddit", "telegram", "producthunt", "devto"]


def plan(opportunity_name: str, category: str, destinations: list):
    site = destinations[0] if destinations else "<your-site>"
    drafts = {
        p: f"[{p}] Our new take on {category} (idea: {opportunity_name}) -> https://{site}"
        for p in PLATFORMS
    }
    return {"published": False, "drafts": drafts,
            "note": "Drafts only. Publishing is disabled until accounts are connected "
                    "and platform/crypto-ad rules are reviewed."}
