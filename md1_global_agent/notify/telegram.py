"""Daily report to the owner's Telegram chat. Never prints the token or chat id."""
import os
import requests


def _creds():
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")
    return token, chat


def send(text: str) -> bool:
    token, chat = _creds()
    if not token or not chat:
        print("Telegram: skipped (no bot token / chat id in secrets)")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"},
            timeout=30,
        )
    except requests.RequestException as exc:
        print(f"Telegram: failed ({type(exc).__name__})")
        return False
    if not resp.ok:
        print(f"Telegram: failed ({resp.status_code}: {resp.text[:200]})")
        return False
    print("Telegram: report sent")
    return True


def daily_report(config, opportunities, report, plan_title, provider, plan_error, issue_hint=""):
    lines = [f"MD1 Scout - تقرير يومي",
             f"الوضع: {'تجريبي (لا نشر)' if config.get('dry_run') else 'نشر فعلي'}",
             f"فرص تم تقييمها: {report['total']}"]
    for o in opportunities[:3]:
        r, a = o["repo"], o["analysis"]
        lines.append(f"- {a['score']} | {o['mode']} | {r['full_name']}")
    if plan_title:
        lines.append(f"الخطة: {plan_title}")
        lines.append(f"النموذج المستخدم: {provider}")
        if issue_hint:
            lines.append(issue_hint)
    elif plan_error:
        lines.append(f"فشل التخطيط: {plan_error[:600]}")
    else:
        lines.append("لا توجد فرصة تعدّت حد البناء اليوم")
    lines.append("نراجع غدا في نفس الموعد.")
    return "\n".join(lines)
