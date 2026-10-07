"""Commercial opportunity scoring."""
import math
from datetime import datetime,timezone
from .license_check import check as license_check
BUYER=("automation","invoice","billing","payment","analytics","monitoring","dashboard","crm","erp","api","workflow","productivity","scheduler","backup","security","compliance","report","converter","generator","editor","search","scraper","integration","email","marketing","ecommerce","shopify","woocommerce","sales","resume","pdf")
def score(repo,config,memory):
    product=repo.get("kind")=="product"
    ok,note=(True,"closed product: rebuild the problem with original code/design/brand") if product else license_check(repo,config.get("allowed_licenses",[]))
    stars=max(int(repo.get("stars",0)),1); days=9999
    if repo.get("pushed_at"):
        days=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(repo["pushed_at"].replace("Z","+00:00"))).days)
    text=(repo.get("full_name","")+" "+repo.get("description","")+" "+" ".join(repo.get("topics",[]))).lower()
    popularity=min(30,math.log10(stars)*8)
    activity=25 if days<30 else 15 if days<180 else 0
    gap=min(20,(int(repo.get("open_issues",0))/stars)*400)
    buyer=min(20,sum(x in text for x in BUYER)*2)
    total=popularity+activity+gap+buyer+(25 if ok else 0)
    if repo.get("archived"): total=0
    return {"score":round(max(0,min(100,total)),1),"license_ok":ok,"license_note":note,
            "days_since_push":days,"buyer_intent":round(buyer,1),
            "demand_signal":round(min(100,popularity+gap+buyer),1),
            "differentiation_question":f"What can we make materially better or easier to buy than {repo['full_name']}?"}
