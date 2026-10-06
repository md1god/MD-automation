"""Daily report to the owner's Telegram chat. Never prints the token or chat id."""
import os
import requests


TOKEN_NAMES = ["BOT_TOKEN", "TELEGRAM_BOT_TOKEN"]
CHAT_NAMES = ["CHAT_ID", "TELEGRAM_CHAT_ID"]


def _clean_token(value: str) -> str:
    """Secrets often carry a trailing newline/space or a leading 'bot' copied from the URL."""
    value = "".join(value.split())
    return value[3:] if value.lower().startswith("bot") and ":" in value[3:] else value


def _hint(err: str) -> str:
    if err.startswith(("404", "401")):
        return " -> Telegram does not accept this TOKEN (revoked, mistyped or from another bot)"
    if "chat not found" in err:
        return " -> token is valid; this bot cannot reach that chat: open the bot and send /start"
    return ""


def _candidates():
    """(token_name, token, chat_name, chat) pairs. Different secrets may belong to different
    bots, so every token/chat combination is tried; only secret NAMES are ever logged."""
    tokens = [(n, _clean_token(os.getenv(n))) for n in TOKEN_NAMES if os.getenv(n, "").strip()]
    chats = [(n, os.getenv(n).strip()) for n in CHAT_NAMES if os.getenv(n, "").strip()]
    seen, out = set(), []
    for tn, tv in tokens:
        for cn, cv in chats:
            if (tv, cv) not in seen:
                seen.add((tv, cv))
                out.append((tn, tv, cn, cv))
    return tokens, out


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


def _post(token, chat, text):
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"},
            timeout=30,
        )
    except requests.RequestException as exc:
        return False, type(exc).__name__
    return resp.ok, ("" if resp.ok else f"{resp.status_code}: {resp.text[:150]}")


def send(text: str, channel: str = "") -> bool:
    tokens, pairs = _candidates()
    if not tokens:
        print("Telegram: skipped - no BOT_TOKEN / TELEGRAM_BOT_TOKEN secret reached the job")
        return False
    for tn, tv, cn, cv in pairs:
        ok, err = _post(tv, cv, text)
        if ok:
            print(f"Telegram: report sent (token={tn}, chat={cn})")
            return True
        print(f"Telegram: {tn} + {cn} failed ({err}){_hint(err)}")
    # Last resort: the private chat that wrote to one of the bots (needs one /start).
    for tn, tv in tokens:
        chat, why = _discover_chat(tv)
        if not chat:
            print(f"Telegram: {tn} discovery failed: {why}")
            continue
        ok, err = _post(tv, chat, text)
        if ok:
            print(f"Telegram: report sent (token={tn}, chat discovered via /start)")
            return True
        print(f"Telegram: {tn} + discovered chat failed ({err})")
    # The daily publisher bot (TELEGRAM_BOT_TOKEN) is known to post to the owner's channel.
    token = dict(tokens).get("TELEGRAM_BOT_TOKEN")
    if channel and token:
        ok, err = _post(token, channel, text)
        if ok:
            print(f"Telegram: report sent to channel {channel} (private chat unavailable; send /start to the bot to receive it privately)")
            return True
        print(f"Telegram: channel {channel} failed ({err})")
    print("Telegram: not delivered")
    return False


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
