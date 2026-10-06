"""Entry point: python main.py  (Dry Run by default, see config.yaml)"""
import yaml

from agent import run


def main():
    with open("config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    opportunities, report = run(config)
    print(f"dry_run={config['dry_run']} | found={report['total']}")
    for o in opportunities[:10]:
        r, a = o["repo"], o["analysis"]
        print(f"{a['score']:5} | {o['mode']:16} | {r['full_name']} | {r['category']} | {a['license_note']}")
    print("Advice:", report["advice"])


if __name__ == "__main__":
    main()
