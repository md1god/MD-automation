"""Union-merge ledger.json with the version on another git ref (used when two runs saved at once).

usage: python merge_ledger.py <their-ref>   (run from the repository root)
Writes the merged ledger over the working copy; entries are never dropped.
"""
import json
import subprocess
import sys

PATH = "md1_global_agent/memory/ledger.json"


def merge(ours: dict, theirs: dict) -> dict:
    out = {"version": 1, "examined": {}, "published": {}}
    for section in ("examined", "published"):
        for src in (theirs, ours):
            for key, val in (src.get(section) or {}).items():
                if key not in out[section] or (val.get("at", "") < out[section][key].get("at", "")):
                    out[section][key] = val
    return out


def main(ref: str) -> None:
    ours = json.load(open(PATH, encoding="utf-8"))
    shown = subprocess.run(["git", "show", f"{ref}:{PATH}"], capture_output=True, text=True)
    theirs = json.loads(shown.stdout) if shown.returncode == 0 and shown.stdout.strip() else {}
    merged = merge(ours, theirs)
    json.dump(merged, open(PATH, "w", encoding="utf-8"), indent=1, ensure_ascii=False, sort_keys=True)
    open(PATH, "a").write("\n")


if __name__ == "__main__":
    main(sys.argv[1])
