import base64, hashlib, json, os, requests
REPO = os.getenv('MDM1_REPO', 'md1god/MDM1.org')
BRANCH = os.getenv('MDM1_BRANCH', 'main')
TOKEN = os.getenv('MDM1_GITHUB_TOKEN')
ROOT = 'pages/opportunities'

def main():
    if not TOKEN:
        print('MDM1_GITHUB_TOKEN missing; skipping page publication')
        return 0
    with open('out/best-opportunity.json', encoding='utf-8') as f: best = json.load(f)
    if not best: return 0
    repo = best['repo']
    seed = (repo['full_name'] + '|' + repo['url']).encode()
    slug = repo['full_name'].lower().replace('/','-') + '-' + hashlib.sha1(seed).hexdigest()[:10]
    path = ROOT + '/' + slug + '.html'
    api = 'https://api.github.com/repos/' + REPO + '/contents/' + path
    headers = {'Accept':'application/vnd.github+json','Authorization':'Bearer ' + TOKEN,'X-GitHub-Api-Version':'2022-11-28','User-Agent':'md1-opportunity-engine'}
    check = requests.get(api, params={'ref': BRANCH}, headers=headers, timeout=30)
    if check.status_code == 200: return 0
    if check.status_code != 404: check.raise_for_status()
    r = repo; a = best['analysis']
    html = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>' + r['full_name'] + ' — MDM1</title></head><body><main>'
    html += '<p>MDM1 · New Opportunity · Score ' + str(a['score']) + '</p><h1>' + r['full_name'] + '</h1>'
    html += '<p>Demand signal: ' + str(a.get('demand_signal',0)) + ' · Mode: ' + best['mode'] + '</p>'
    html += '<p>Independent product. Closed products are rebuilt from the problem only; open-source reuse follows applicable licenses.</p>'
    html += '<p><a href="' + r['url'] + '" rel="nofollow">Market reference</a></p><p><a href="https://t.me/md1god">Request early access</a></p></main></body></html>'
    encoded = base64.b64encode(html.encode()).decode()
    resp = requests.put(api, headers=headers, json={'message':'Add opportunity page: ' + slug,'content':encoded,'branch':BRANCH}, timeout=30)
    resp.raise_for_status()
    print('MDM1 page created: https://mdm1.org/' + path)
    return 0

if __name__ == '__main__': raise SystemExit(main())