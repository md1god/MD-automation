"""Orchestrates the roles: Scout -> Investigator/Strategist -> Builder/Monetizer/Distributor -> Analyst -> Memory."""
from discovery.github_source import scout
from analysis.scorer import score
from builder.builder import plan as builder_plan
from monetization.monetizer import suggest
from distribution.distributor import plan as distribution_plan
from analytics.analyst import summarize
from memory import store


def run(config: dict):
    memory = store.load(config["memory_file"])
    repos = scout(config)
    opportunities = []
    for repo in repos:
        analysis = score(repo, config, memory)
        item = {"repo": repo, "analysis": analysis}
        if analysis["score"] >= config["min_score_to_build"]:
            item["builder"] = builder_plan(repo, analysis, config["max_fix_cycles"], config["dry_run"])
            item["monetization"] = suggest(repo)
            item["distribution"] = distribution_plan(repo, config["dry_run"])
        opportunities.append(item)
    opportunities.sort(key=lambda o: o["analysis"]["score"], reverse=True)
    report = summarize(opportunities)
    memory["runs"].append({"total": report["total"], "advice": report["advice"]})
    store.save(config["memory_file"], memory)
    return opportunities, report
