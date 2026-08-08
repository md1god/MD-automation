import json
import os
from datetime import datetime, timezone

STATS_FILE = os.path.join(os.path.dirname(__file__), "publish_log.json")


def log_publish(platform: str, post_id: str, success: bool, error: str = None):
    """يسجل كل محاولة نشر في ملف JSON بسيط للمتابعة."""
    entry = {
        "platform": platform,
        "post_id": post_id,
        "success": success,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    logs = []
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            logs = []

    logs.append(entry)

    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

    status = "✅ نجح" if success else f"❌ فشل: {error}"
    print(f"[{platform}] {post_id} — {status}")
