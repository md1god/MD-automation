"""Opportunity engine entry point."""
import yaml
from agent import run
from builder.planner import make_plan
from notify import telegram
def main():
    with open("config.yaml",encoding="utf-8") as f: config=yaml.safe_load(f)
    opportunities,report=run(config)
    print(f"dry_run={config['dry_run']} | found={report['total']}")
    for o in opportunities[:10]:
        r,a=o["repo"],o["analysis"]; print(f"{a['score']:5} | {o['mode']:16} | {r['full_name']} | {r['category']}")
    title,error=write_plan(opportunities,config.get("llm",{}))
    telegram.send(channel=config.get("telegram_report_channel",""),text=telegram.daily_report(config,opportunities,report,title,make_plan.used,error,"MVP build is isolated; existing MDM1 pages are never modified."))
def write_plan(opportunities,llm=None):
    best=next((o for o in opportunities if "builder" in o),None)
    if not best: return None,None
    try: text=make_plan(best,llm)
    except Exception as e: return None,str(e)
    title=f"{best['repo']['full_name']} ({best['mode']}, score {best['analysis']['score']})"
    with open("plan.md","w",encoding="utf-8") as f: f.write(f"# {title}\n\n{best['repo']['url']}\n\n{text}\n")
    return title,None
if __name__=="__main__": main()
