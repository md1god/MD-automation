"""Memory role: remembers what worked and what failed."""
import json
from pathlib import Path


def load(path: str):
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text())
    return {"categories": {}, "runs": []}


def save(path: str, data: dict):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def record_outcome(data: dict, category: str, success: bool):
    c = data["categories"].setdefault(category, {"wins": 0, "fails": 0})
    c["wins" if success else "fails"] += 1
