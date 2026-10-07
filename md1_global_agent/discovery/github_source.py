"""GitHub opportunity discovery."""
import os
from datetime import datetime, timedelta, timezone
import requests
API="https://api.github.com/search/repositories"
def _headers():
    h={"Accept":"application/vnd.github+json","User-Agent":"md1-global-agent"}
    if os.getenv("GITHUB_TOKEN"): h["Authorization"]="Bearer "+os.environ["GITHUB_TOKEN"]
    return h
def search(query,limit=10,sort="stars"):
    r=requests.get(API,params={"q":query,"sort":sort,"order":"desc","per_page":limit},headers=_headers(),timeout=20)
    r.raise_for_status()
    out=[]
    for it in r.json().get("items",[]):
        out.append({"full_name":it["full_name"],"url":it["html_url"],"description":it.get("description") or "",
                    "stars":it.get("stargazers_count",0),"forks":it.get("forks_count",0),
                    "open_issues":it.get("open_issues_count",0),"pushed_at":it.get("pushed_at"),
                    "license":((it.get("license") or {}).get("spdx_id") or "").lower(),
                    "archived":it.get("archived",False),"topics":it.get("topics",[])})
    return out
def scout(config):
    found=[]
    for category,spec in config.get("categories",{}).items():
        try:
            for r in search(spec["query"],config.get("max_results_per_query",10)):
                r["category"]=category; found.append(r)
        except Exception as e: print(f"[scout] {category} failed: {e}")
    since=(datetime.now(timezone.utc)-timedelta(days=30)).date().isoformat()
    try:
        for r in search(f"stars:>=25 pushed:>={since} archived:false",max(20,config.get("max_results_per_query",10)*2),"updated"):
            r["category"]="rising_all"; found.append(r)
    except Exception as e: print(f"[scout] rising_all failed: {e}")
    unique={r["full_name"]:r for r in found}
    return list(unique.values())
