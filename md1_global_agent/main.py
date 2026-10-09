"""Entry point: python main.py

Daily flow: retry pending pages -> discover NEW opportunities -> plan the best one in Arabic ->
translate -> quality gate -> publish a real multilingual page on mdm1.org and verify it is live ->
promote it on the Telegram channel -> Arabic Telegram report to the owner.

Everything printed here goes to PUBLIC workflow logs, so only opaque ids are ever printed.
"""
import json
import time
from pathlib import Path

import yaml

from agent import run
from builder.planner import make_plan
from memory.ledger import Ledger, key_for, public_id
from notify import telegram
from privacy import identity_terms
from publish import mdm1_page
from publish.translate import translate_all

LEGACY_PLANNED = Path("memory/planned.json")


def migrate_legacy(ledger: Ledger) -> None:
    """Old memory/planned.json stored plain project names in a public repo: hash them, then delete it."""
    if LEGACY_PLANNED.exists():
        names = json.loads(LEGACY_PLANNED.read_text(encoding="utf-8")).keys()
        added = ledger.import_legacy_names(names)
        LEGACY_PLANNED.unlink()
        print(f"Ledger: migrated {added} legacy entries")


def announce(payload: dict, outcome: dict, config: dict) -> bool:
    """Promote a published page on the channel (sanitized text only)."""
    codes = ["ar"] + list((payload.get("translations") or {}).keys())
    return telegram.send_channel(telegram.promo_text(payload, outcome["url"], codes),
                                 config.get("telegram_report_channel", ""))


def retry_pending(ledger: Ledger, config: dict) -> list:
    """Pages whose publishing failed earlier (e.g. expired token). Returns (id, result) pairs."""
    results = []
    for payload in mdm1_page.load_pending():
        outcome = mdm1_page.publish(payload, mdm1_page.env_token())
        print(f"Pending {payload['id']}: {outcome['state']} {outcome['reason']}")
        if outcome["state"] == "published":
            if payload.get("ledger_key"):
                ledger.mark_published_key(payload["ledger_key"], outcome["url"])
            announce(payload, outcome, config)
            mdm1_page.drop_pending(payload["id"])
        results.append((payload["id"], outcome))
    return results


def plan_and_publish(best: dict, config: dict, ledger: Ledger):
    """Plan `best`, translate, gate, publish. Returns (plan_error, outcome, provider, payload, promo_sent)."""
    llm = config.get("llm", {})
    name = best["repo"]["full_name"]
    pub_id = public_id(name)
    try:
        plan_md = make_plan(best, llm)
    except Exception as exc:
        print(f"Plan {pub_id}: failed ({str(exc)[:200]})")
        return str(exc), None, None, None, False
    provider = make_plan.used
    terms = identity_terms(best["repo"])
    try:
        payload = mdm1_page.build_payload(plan_md, pub_id, terms, key_for(name))
    except mdm1_page.PageRejected as exc:
        print(f"Plan {pub_id}: page rejected - {exc}")
        return None, {"state": "failed", "url": "", "reason": f"رُفضت الصفحة: {exc}"}, provider, None, False
    payload["translations"] = translate_all(payload, terms, llm, config.get("page_languages", []),
                                            budget=config.get("translate_budget_seconds", 900))
    outcome = mdm1_page.publish(payload, mdm1_page.env_token())
    print(f"Publish {pub_id}: {outcome['state']} {outcome['reason']}")
    promo_sent = False
    if outcome["state"] == "published":
        ledger.mark_published(name, outcome["url"])
        promo_sent = announce(payload, outcome, config)
    else:
        mdm1_page.save_pending(payload)          # sanitized text only; retried next run
    return None, outcome, provider, payload, promo_sent


def private_details(top: list, best) -> str:
    """id -> source mapping. Sent ONLY to a private chat; never printed or committed."""
    lines = ["MD1 Scout - تفاصيل المصدر (سري، لك فقط)"]
    for o in top:
        r = o["repo"]
        mark = " ← الخطة" if best and r["full_name"] == best["repo"]["full_name"] else ""
        lines.append(f"فرصة {public_id(r['full_name'])}: {r['full_name']}\n{r['url']}{mark}")
    return "\n\n".join(lines)


def main():
    with open("config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    ledger = Ledger()
    migrate_legacy(ledger)
    retried = retry_pending(ledger, config)

    opportunities, report = run(config, ledger)
    print(f"dry_run={config['dry_run']} | new_opportunities={report['total']}")
    for o in opportunities[:10]:
        r, a = o["repo"], o["analysis"]
        print(f"{a['score']:5} | {o['mode']:16} | {public_id(r['full_name'])} | {r['category']}")
    print("Advice:", report["advice"])

    best = next((o for o in opportunities if "builder" in o), None)
    plan_error = outcome = provider = payload = None
    promo_sent = False
    if best:
        plan_error, outcome, provider, payload, promo_sent = plan_and_publish(best, config, ledger)
    else:
        print("Plan: no NEW opportunity passed the build threshold")

    planned = best if best and not plan_error else None
    page = ({"title": payload["title"], "languages": ["ar"] + list(payload["translations"])}
            if payload else None)
    text = telegram.daily_report(config, opportunities, report,
                                 public_id(planned["repo"]["full_name"]) if planned else None,
                                 provider, plan_error, outcome, page, promo_sent, retried)
    delivered = telegram.send(channel=config.get("telegram_report_channel", ""), text=text)
    top = opportunities[:3]
    if delivered:
        telegram.send_private(private_details(top, planned))
        for o in top:                              # level 1: what was shown is never shown again
            if plan_error and o is best:
                continue                           # a failed plan is retried tomorrow
            ledger.mark_examined(o["repo"]["full_name"])
    if planned:
        ledger.mark_examined(planned["repo"]["full_name"], "planned")
    ledger.save()


if __name__ == "__main__":
    main()
