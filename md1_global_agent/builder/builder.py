"""Builder role: Analyze -> Plan -> Modify/Build -> Test -> Fix loop (capped).

In dry_run it only produces the plan. A real run needs a git/PR backend wired in.
Modes:
  modify            open-source with a commercial-friendly license; keeps the license notice
  rebuild_original  closed product; only the idea is used, code/design/name are new
Never writes to main (always a branch + Pull Request).
"""


def plan(repo: dict, analysis: dict, mode: str, max_fix_cycles: int = 3, dry_run: bool = True):
    if mode == "skip":
        return {"status": "blocked", "reason": analysis["license_note"]}
    if mode == "rebuild_original":
        head = [
            "research the product: idea, audience, pricing, user complaints",
            "write an original spec that solves the same problem better",
            "choose a NEW name, brand, design and copy (nothing copied from the source)",
            "write all code from scratch",
        ]
    else:
        head = [
            "create branch agent/<slug>",
            "keep LICENSE + copyright notice; add attribution",
            "read README + architecture",
            "choose files to change and modify code",
        ]
    steps = head + [
        "add tests; run build / lint / test",
        f"if failing: diagnose -> fix -> retest (max {max_fix_cycles} cycles)",
        "differentiation check: is there a real reason to choose ours?",
        "open Pull Request (never push to main)",
    ]
    return {"status": "planned" if dry_run else "ready", "mode": mode, "steps": steps,
            "max_fix_cycles": max_fix_cycles}
