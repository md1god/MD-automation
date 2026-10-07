"""Orchestrates the roles: Scout -> Investigator/Strategist -> Builder/Monetizer/Distributor -> Analyst -> Memory."""
from discovery.github_source import scout as scout_github
from discovery.products_source import scout as scout_products
from analysis.scorer import score
from analysis.classifier import mode as classify
from builder.builder import plan as builder_plan
from monetization.monetizer import suggest
from distribution.distributor import plan as distribution_plan
from analytics.analyst import summarize
from memory import store
from discovery.research_source import scout as scout_research


def scout(config: dict):
    return scout_research(config) + scout_github(config) + scout_products(config)


def run(config: dict):
    memory = store.load(config["memory_file"])
    repos = scout(config)
    opportunities = []
    for repo in repos:
        analysis = score(repo, config, memory)
        build_mode = classify(repo, analysis, config)
        item = {"repo": repo, "analysis": analysis, "mode": build_mode}
        if build_mode != "skip" and analysis["score"] >= config["min_score_to_build"]:
            item["builder"] = builder_plan(repo, analysis, build_mode,
                                           config["max_fix_cycles"], config["dry_run"])
            item["monetization"] = suggest(repo)
            item["distribution"] = distribution_plan(repo["full_name"], repo["category"],
                                                     config.get("destinations", []))
        opportunities.append(item)
    opportunities.sort(key=lambda o: o["analysis"]["score"], reverse=True)
    report = summarize(opportunities)
    memory["runs"].append({"total": report["total"], "advice": report["advice"]})
    store.save(config["memory_file"], memory)
    return opportunities, report
