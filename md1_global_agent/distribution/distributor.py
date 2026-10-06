"""Distributor role: prepares platform-specific content. Never posts in dry_run."""

PLATFORMS = ["x", "reddit", "telegram", "producthunt", "devto"]


def plan(repo: dict, dry_run: bool = True):
    drafts = {
        p: f"[{p}] New take on {repo['category']}: inspired by {repo['full_name']} — "
        f"what would you want improved?"
        for p in PLATFORMS
    }
    return {"published": False, "drafts": drafts,
            "note": "Publishing is disabled until accounts are connected."}
