"""Builder role: Analyze -> Plan -> Modify -> Test -> Fix loop (capped).

In dry_run it only produces the plan. A real run needs a git/PR backend wired in.
It refuses projects whose license does not allow commercial use and never writes to main.
"""


def plan(repo: dict, analysis: dict, max_fix_cycles: int = 3, dry_run: bool = True):
    if not analysis["license_ok"]:
        return {"status": "blocked", "reason": analysis["license_note"]}
    steps = [
        "create branch agent/<slug>",
        "read README + architecture",
        "choose files to change",
        "modify code + add tests",
        "run build / lint / test",
        f"if failing: diagnose -> fix -> retest (max {max_fix_cycles} cycles)",
        "differentiation check",
        "open Pull Request (never push to main)",
    ]
    return {"status": "planned" if dry_run else "ready", "steps": steps,
            "max_fix_cycles": max_fix_cycles}
