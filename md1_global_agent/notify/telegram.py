"""Daily report to the owner's Telegram chat. Never prints secrets or source identities."""
import os
import requests

from memory.ledger import public_id


TOKEN_NAMES = ["BOT_TOKEN", "TELEGRAM_BOT_TOKEN"]
CHAT_NAMES = ["CHAT_ID", "TELEGRAM_CHAT_ID"]
OWNER_CHAT_NAME = "OWNER_CHAT_ID"      # the owner's PRIVATE chat id (positive number); optional but most reliable


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


def chat_is_private(token: str, chat: str) -> bool:
    """True only for a one-to-one chat. Source identities are never posted anywhere else."""
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/getChat", params={"chat_id": chat}, timeout=30)
        return resp.ok and (resp.json().get("result") or {}).get("type") == "private"
    except (requests.RequestException, ValueError):
        return False


def send_private(text: str) -> bool:
    """Owner-only message (plan text, id -> source mapping). Never goes to a channel or group.

    Order: OWNER_CHAT_ID secret -> CHAT_ID secrets that turn out to be private chats ->
    a private chat discovered via getUpdates (needs /start sent to the bot in the last 24h).
    Only secret NAMES and reasons are printed, never ids or tokens.
    """
    tokens, pairs = _candidates()
    owner = os.getenv(OWNER_CHAT_NAME, "").strip()
    targets = []
    if owner:
        if owner.lstrip("-").isdigit() and not owner.startswith("-"):
            targets += [(tn, tv, owner, True) for tn, tv in tokens]
        else:
            print("Telegram: OWNER_CHAT_ID ignored - a private chat id is a positive number (channels/groups are negative)")
    targets += [(tn, tv, cv, False) for tn, tv, _cn, cv in pairs]
    for tn, tv in tokens:
        chat, why = _discover_chat(tv)
        if chat:
            targets.append((tn, tv, chat, False))
        else:
            print(f"Telegram: {tn} discovery: {why}")
    for tn, tv, chat, trusted in targets:
        if not trusted and not chat_is_private(tv, chat):
            continue
        ok, err = _post(tv, chat, text)
        if ok:
            print(f"Telegram: private message sent (token={tn})")
            return True
        print(f"Telegram: private send via {tn} failed ({err[:80]}){_hint(err)}")
    print("Telegram: private message NOT sent - set the OWNER_CHAT_ID secret (your private chat id), "
          "and press Start on the bot")
    return False


def send_channel(text: str, channel: str) -> bool:
    """Public promotion post to the owner's channel. Callers pass sanitized text only."""
    if not channel:
        return False
    tokens, _ = _candidates()
    for tn, tv in tokens:
        ok, err = _post(tv, channel, text)
        if ok:
            print(f"Telegram: promo posted to channel (token={tn})")
            return True
        print(f"Telegram: promo via {tn} failed ({err})")
    return False


def promo_text(payload: dict, url: str, language_codes) -> str:
    """Arabic first (the owner's audience) + English line; the page itself opens in the visitor's language."""
    en = (payload.get("translations") or {}).get("en")
    lines = ["🆕 مشروع جديد قيد الدراسة على MDM1", "", payload["title"], payload["description"]]
    if en:
        lines += ["", f"🌍 {en['title']}", en["description"]]
    lines += ["", f"🔗 {url}",
              f"الصفحة تفتح تلقائيًا بلغة جهازك ({len(list(language_codes))} لغات) ويمكنك تغييرها من زر 🌐 أعلى الصفحة.",
              "#MDM1 #مشاريع_جديدة"]
    return "\n".join(lines)


def opaque(repo: dict) -> str:
    return public_id(repo["full_name"])


def daily_report(config, opportunities, report, plan_id, provider, plan_error, publish=None,
                 page=None, promo_sent=None, retried=None):
    """Owner report (Arabic). Only opaque ids appear - no project name or URL of the source.

    publish = {"state": "published" | "failed", "url", "reason"} or None
    page    = {"title": str, "languages": [codes]} for the page that was just built
    """
    lines = ["MD1 Scout - تقرير يومي",
             f"الوضع: {'تجريبي (لا نشر)' if config.get('dry_run') else 'تشغيل فعلي'}",
             f"فرص جديدة تم تقييمها: {report['total']}"]
    for o in opportunities[:3]:
        r, a = o["repo"], o["analysis"]
        lines.append(f"- {a['score']} | {o['mode']} | فرصة {opaque(r)} | {r['category']}")
    for pid, outcome in (retried or []):
        if outcome["state"] == "published":
            lines.append(f"♻️ إعادة محاولة ناجحة لفرصة {pid}: {outcome['url']}")
    if plan_id:
        lines.append(f"الخطة: فرصة {plan_id} (النموذج: {provider})")
        if publish and publish["state"] == "published":
            langs = ", ".join((page or {}).get("languages", []))
            lines += ["", "✅ تم النشر فعليًا",
                      f"العنوان: {(page or {}).get('title', '')}",
                      f"الرابط: {publish['url']}",
                      f"اللغات ({len((page or {}).get('languages', []))}): {langs}",
                      "الترويج في القناة: " + ("تم ✅" if promo_sent else "لم يتم ⚠️")]
        elif publish and publish["state"] == "held_unsent":
            lines += ["", "⚠️ الخطة جاهزة لكن لم تصلك: لا توجد محادثة خاصة بينك وبين البوت.",
                      "الحل: اضغط Start على البوت، وأضف سر OWNER_CHAT_ID (رقم محادثتك الخاصة).",
                      "ستُعاد المحاولة تلقائيًا في التشغيل القادم."]
        elif publish and publish["state"] == "held":
            lines += ["", "⏸️ النشر على الموقع متوقف حتى يوجد مشروع مكتمل.",
                      "الخطة وصلتك للمراجعة في رسالة خاصة منفصلة."]
        elif publish:
            lines += ["", f"⚠️ الخطة جاهزة لكن النشر لم يتم: {publish['reason']}",
                      "ستُعاد المحاولة تلقائيًا في التشغيل القادم."]
        lines.append("تفاصيل المصدر تصلك في رسالة خاصة منفصلة.")
    elif plan_error:
        lines.append(f"فشل التخطيط: {plan_error[:600]}")
    else:
        lines.append("لا توجد فرصة جديدة تعدّت حد البناء اليوم")
    lines.append("نراجع غدا في نفس الموعد.")
    return "\n".join(lines)
