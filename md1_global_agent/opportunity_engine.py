import hashlib
import json
import os
import re
import yaml

from agent import run
from builder.planner import make_plan
from notify import telegram

def slug_for(repo):
    raw = (repo.get('full_name','') + '|' + repo.get('url','')).encode()
    digest = hashlib.sha1(raw).hexdigest()[:10]
    name = re.sub(r'[^a-z0-9]+', '-', repo.get('full_name','opportunity').lower()).strip('-')
    return (name[:48] or 'opportunity') + '-' + digest

def main():
    with open('config.yaml', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    opportunities, report = run(config)
    candidates = [x for x in opportunities if 'builder' in x and x['mode'] != 'skip']
    best = candidates[0] if candidates else None
    os.makedirs('out', exist_ok=True)
    with open('out/opportunities.json', 'w', encoding='utf-8') as f:
        json.dump({'report': report, 'opportunities': opportunities}, f, ensure_ascii=False, indent=2)
    if not best:
        with open('out/best-opportunity.json', 'w', encoding='utf-8') as f:
            json.dump(None, f)
        telegram.send(channel=config.get('telegram_report_channel',''), text='MD1 Scout: no buildable opportunity today.')
        return 0
    try:
        plan = make_plan(best, config.get('llm', {}))
        provider = make_plan.used or 'unknown'
    except Exception as exc:
        provider = 'fallback'
        plan = 'Build an original MVP around the validated problem. Keep it small, differentiated and sellable. Error: ' + str(exc)[:160]
    slug = slug_for(best['repo'])
    with open('opportunity_slug.txt','w',encoding='utf-8') as f: f.write(slug)
    with open('plan.md','w',encoding='utf-8') as f: f.write('# ' + best['repo']['full_name'] + '\n\n' + best['repo']['url'] + '\n\n' + plan + '\n')
    request = ('Build an original sellable MVP only under products/' + slug + '/. '
               'Do not modify existing site pages. Closed products: use only the problem/idea; never copy code, assets, branding or UI. '
               'Open source: reuse only with commercial-compatible license and preserve attribution. Include README, monetization notes and a smoke test.\n\nPlanner:\n' + plan)
    with open('build_request.md','w',encoding='utf-8') as f: f.write(request)
    best_out = {'repo': best['repo'], 'analysis': best['analysis'], 'mode': best['mode'], 'monetization': best.get('monetization'), 'distribution': best.get('distribution')}
    with open('out/best-opportunity.json','w',encoding='utf-8') as f: json.dump(best_out, f, ensure_ascii=False, indent=2)
    telegram.send(channel=config.get('telegram_report_channel',''), text='MD1 Scout: ' + best['repo']['full_name'] + ' | score=' + str(best['analysis']['score']) + ' | mode=' + best['mode'] + ' | planner=' + provider)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())