"""Daily report to the owner's Telegram chat. Never prints the token or chat id."""
import os
import requests


def _creds():
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")
    return token, chat


def _discover_chat(token: str):
    """Find the owner's private chat: the most recent private chat that wrote to the bot."""
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30)
    except requests.RequestException as exc:
        return None, f"getUpdates failed ({type(exc).__name__})"
    if not resp.ok:
        return None, f"getUpdates {resp.status_code}: {resp.text[:150]}"
    for update in reversed(resp.json().get("result", [])):
        msg = update.get("message") or update.get("my_chat_member") or {}
        chat = msg.get("chat") or {}
        if chat.get("type") == "private" and chat.get("id"):
            return str(chat["id"]), None
    return None, "no private chat found: open the bot in Telegram and send it /start once"


def send(text: str) -> bool:
    token, chat = _creds()
    if not token:
        print("Telegram: skipped - no TELEGRAM_BOT_TOKEN / BOT_TOKEN secret reached the job")
        return False
    if not chat:
        chat, why = _discover_chat(token)
        if not chat:
            print(f"Telegram: skipped - no TELEGRAM_CHAT_ID secret and discovery failed: {why}")
            return False
        print("Telegram: chat id discovered automatically; add it as TELEGRAM_CHAT_ID secret to make it permanent")
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
