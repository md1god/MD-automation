"""Choose lawful build mode."""
HARDWARE=("e-ink","eink","hardware","raspberry pi","arduino","esp32","3d print","drone","robot kit","sensor","pcb","firmware","wearable","device","gadget","kit")
def mode(repo,analysis):
    text=f"{repo.get('full_name','')} {repo.get('description','')}".lower()
    if repo.get("archived") or any(x in text for x in HARDWARE): return "skip"
    if repo.get("kind")=="product": return "rebuild_original"
    return "modify" if analysis["license_ok"] else "skip"
