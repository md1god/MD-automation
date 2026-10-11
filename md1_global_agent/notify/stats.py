"""Daily owner statistics (separate from the publish links): what was found, what was published, what is missing."""
import os
from collections import Counter
from datetime import datetime, timezone


def due() -> bool:
    """Once a day: the 06:00 UTC scheduled run (09:00 Cairo), or any run with STATS_FORCE=1."""
    return os.getenv("STATS_FORCE") == "1" or datetime.now(timezone.utc).hour == 6


def message(ledger, report: dict, run: dict) -> str:
    how = Counter(v.get("how", "?") for v in ledger.data["examined"].values())
    pub = len(ledger.data["published"])
    lines = ["📊 الحصيلة اليومية — MD1 Scout", "",
             "🔎 البحث",
             f"• فرص جديدة في هذه الجولة: {report.get('total', 0)}",
             f"• إجمالي ما فُحص منذ البداية: {len(ledger.data['examined'])}",
             "",
             "✅ المنشور (إجمالي)",
             f"• صفحات خطط: {pub}",
             f"• أدوات: {how.get('tool-published', 0)}",
             f"• تطبيقات: {how.get('app-published', 0)}",
             "",
             "🧮 هذه الجولة",
             f"• خطط نُشرت: {run.get('plans', 0)} | تطبيقات: {run.get('apps', 0)} | أدوات: {run.get('tools', 0)}",
             f"• بانتظار النشر (مؤهلة ولم يصلها الدور): {run.get('waiting', 0)}",
             "",
             "⚠️ الناقص",
             f"• أفكار تطبيقات فشل بناؤها: {how.get('app-failed', 0)}",
             f"• ترويج اجتماعي: {'مفعّل' if run.get('social') else 'غير مربوط (لا حسابات/مفاتيح)'}"]
    return "\n".join(lines)
