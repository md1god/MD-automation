"""Monetizer role: suggests the best income model per category."""

MODELS = {
    "saas": ["Hosted subscription", "Paid templates/starter kit", "Paid support"],
    "ai_agents": ["Usage-based API", "Hosted agents subscription", "Consulting packs"],
    "developer_tools": ["Pro tier / team plan", "Sponsorship", "Hosted version"],
    "ecommerce": ["Marketplace fee", "Premium themes/plugins", "Affiliate/referral"],
    "productivity": ["Freemium subscription", "Lifetime deal", "Team plan"],
    "apis": ["Metered API pricing", "Enterprise plan", "Marketplace listing"],
}


def suggest(repo: dict):
    return MODELS.get(repo["category"], ["Freemium", "Sponsorship"])
