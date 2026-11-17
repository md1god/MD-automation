import http from 'node:http';
import crypto from 'node:crypto';
import { safeEqual, esc, scrub } from './lib/util.mjs';
import { createGuard } from './lib/guard.mjs';
import { listPlatforms, publish } from './lib/publisher.mjs';
import { discoverSocialLinks } from './lib/discover.mjs';

const MAX_BODY = 200_000;
const TOOLS = [
  { name: 'list_platforms', description: 'List publishing platforms, their character limits and whether each is configured on this server.', inputSchema: { type: 'object', properties: {} } },
  { name: 'publish_post', description: 'Publish a post to one or more configured platforms (bluesky, mastodon, telegram, discord, linkedin, x, facebook, reddit, devto, wordpress, github, webhook). Use dry_run first if unsure. Duplicate posts within 24h and more than the hourly cap per platform are blocked.', inputSchema: { type: 'object', required: ['text', 'platforms'], properties: { text: { type: 'string', description: 'Final post text. Must respect each platform limit.' }, platforms: { type: 'array', items: { type: 'string' } }, title: { type: 'string', description: 'Optional title for article-style platforms (reddit, devto, wordpress).' }, link: { type: 'string' }, options: { type: 'object', description: 'Per-platform options, e.g. {"subreddit":"name","tags":["a","b"]}' }, dry_run: { type: 'boolean' } } } },
  { name: 'discover_social_links', description: 'Fetch a public https web page and return the social profile links it exposes (X, LinkedIn, Facebook, Instagram, YouTube, TikTok, Telegram, GitHub, Bluesky, Threads, Pinterest, Reddit, Discord).', inputSchema: { type: 'object', required: ['url'], properties: { url: { type: 'string' } } } },
];

export function createApp({ env = process.env, guard = createGuard({ perHour: Number(env.RATE_LIMIT_PER_HOUR) || 10 }), discover = discoverSocialLinks } = {}) {
  const apiKey = env.API_KEY || '';
  const oauthStates = new Map();

  const send = (res, code, obj, type = 'application/json; charset=utf-8') => {
    const body = typeof obj === 'string' ? obj : JSON.stringify(obj);
    res.writeHead(code, { 'Content-Type': type, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    res.end(body);
  };
  const readBody = (req) => new Promise((resolve, reject) => {
    let n = 0; const chunks = [];
    req.on('data', (c) => { n += c.length; if (n > MAX_BODY) { reject(new Error('body too large')); req.destroy(); } else chunks.push(c); });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
  const authed = (req, url, pathKey, allowQuery = false) => {
    if (!apiKey) return false;
    const h = req.headers.authorization || '';
    const given = pathKey || (h.startsWith('Bearer ') ? h.slice(7) : '') || (allowQuery ? url.searchParams.get('key') : '') || '';
    return given.length > 0 && safeEqual(given, apiKey);
  };

  async function runTool(name, args) {
    if (name === 'list_platforms') return listPlatforms(env);
    if (name === 'publish_post') return publish(args || {}, { env, guard });
    if (name === 'discover_social_links') return discover(String((args || {}).url || ''));
    throw new Error('unknown tool');
  }

  async function mcp(req, res, body) {
    let msg;
    try { msg = JSON.parse(body); } catch { return send(res, 400, { jsonrpc: '2.0', id: null, error: { code: -32700, message: 'parse error' } }); }
    const one = async (m) => {
      if (!m || m.jsonrpc !== '2.0' || typeof m.method !== 'string') return { jsonrpc: '2.0', id: (m && m.id) ?? null, error: { code: -32600, message: 'invalid request' } };
      if (m.id === undefined) return null; // notification
      const ok = (result) => ({ jsonrpc: '2.0', id: m.id, result });
      if (m.method === 'initialize') return ok({ protocolVersion: (m.params && m.params.protocolVersion) || '2025-03-26', capabilities: { tools: {} }, serverInfo: { name: 'md1-publisher', version: '1.0.0' } });
      if (m.method === 'ping') return ok({});
      if (m.method === 'tools/list') return ok({ tools: TOOLS });
      if (m.method === 'tools/call') {
        try {
          const out = await runTool(m.params && m.params.name, m.params && m.params.arguments);
          return ok({ content: [{ type: 'text', text: JSON.stringify(out) }], isError: out && out.ok === false });
        } catch (e) { return ok({ content: [{ type: 'text', text: scrub(e.message, env) }], isError: true }); }
      }
      return { jsonrpc: '2.0', id: m.id, error: { code: -32601, message: 'method not found' } };
    };
    const out = Array.isArray(msg) ? (await Promise.all(msg.map(one))).filter(Boolean) : await one(msg);
    if (out === null || (Array.isArray(out) && !out.length)) { res.writeHead(202); return res.end(); }
    return send(res, 200, out);
  }

  async function linkedinOAuth(req, res, url) {
    const id = env.LINKEDIN_CLIENT_ID, secret = env.LINKEDIN_CLIENT_SECRET, base = (env.PUBLIC_URL || '').replace(/\/+$/, '');
    if (!id || !secret || !base) return send(res, 400, 'Set LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET and PUBLIC_URL first.', 'text/plain; charset=utf-8');
    const redirect = `${base}/oauth/linkedin/callback`;
    if (url.pathname.endsWith('/start')) {
      const state = crypto.randomBytes(16).toString('hex'); oauthStates.set(state, Date.now());
      const q = new URLSearchParams({ response_type: 'code', client_id: id, redirect_uri: redirect, state, scope: 'openid profile w_member_social' });
      res.writeHead(302, { Location: 'https://www.linkedin.com/oauth/v2/authorization?' + q }); return res.end();
    }
    const st = url.searchParams.get('state');
    const t0 = oauthStates.get(st); oauthStates.delete(st);
    if (!t0 || Date.now() - t0 > 600_000) return send(res, 400, 'Invalid or expired state. Start again from /oauth/linkedin/start.', 'text/plain; charset=utf-8');
    const code = url.searchParams.get('code');
    if (!code) return send(res, 400, 'Missing code: ' + esc(url.searchParams.get('error_description') || ''), 'text/plain; charset=utf-8');
    const tr = await fetch('https://www.linkedin.com/oauth/v2/accessToken', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ grant_type: 'authorization_code', code, redirect_uri: redirect, client_id: id, client_secret: secret }) });
    const tj = await tr.json().catch(() => ({}));
    if (!tr.ok || !tj.access_token) return send(res, 502, 'LinkedIn token exchange failed.', 'text/plain; charset=utf-8');
    const ur = await fetch('https://api.linkedin.com/v2/userinfo', { headers: { Authorization: 'Bearer ' + tj.access_token } });
    const uj = await ur.json().catch(() => ({}));
    const days = tj.expires_in ? Math.round(tj.expires_in / 86400) : '?';
    return send(res, 200, `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>LinkedIn</title><body style="font-family:system-ui;max-width:640px;margin:2rem auto;padding:0 1rem;line-height:1.8"><h2>تم ربط LinkedIn</h2><p>انسخ القيمتين التاليتين إلى Environment في Render ثم أعد النشر. الرمز صالح نحو ${esc(days)} يومًا ثم كرّر الربط.</p><p><b>LINKEDIN_AUTHOR_URN</b><br><code>urn:li:person:${esc(uj.sub || '?')}</code></p><p><b>LINKEDIN_ACCESS_TOKEN</b><br><textarea readonly rows="5" style="width:100%">${esc(tj.access_token)}</textarea></p></body>`, 'text/html; charset=utf-8');
  }

  return http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://localhost');
      const p = url.pathname;
      if (p === '/health') return send(res, 200, { ok: true });
      const mcpKey = p.startsWith('/mcp/') ? decodeURIComponent(p.slice(5)) : null;
      if (!(p === '/mcp' || mcpKey !== null) && !['/platforms', '/publish', '/discover', '/oauth/linkedin/start', '/oauth/linkedin/callback'].includes(p)) return send(res, 404, { error: 'not found' });
      if (p === '/oauth/linkedin/callback') { return await linkedinOAuth(req, res, url); } // protected by single-use state
      if (!authed(req, url, mcpKey, p === '/oauth/linkedin/start')) return send(res, 401, { error: 'unauthorized' });
      if (p === '/oauth/linkedin/start') return await linkedinOAuth(req, res, url);
      if (p === '/platforms' && req.method === 'GET') return send(res, 200, { platforms: listPlatforms(env) });
      if (req.method !== 'POST') return send(res, 405, { error: 'method not allowed' });
      const body = await readBody(req);
      if (p === '/mcp' || mcpKey !== null) return await mcp(req, res, body);
      let args; try { args = JSON.parse(body || '{}'); } catch { return send(res, 400, { error: 'invalid json' }); }
      if (p === '/publish') { const out = await publish(args, { env, guard }); return send(res, out.error ? 400 : 200, out); }
      if (p === '/discover') { try { return send(res, 200, await discover(String(args.url || ''))); } catch (e) { return send(res, 400, { error: scrub(e.message, env) }); } }
    } catch (e) {
      send(res, 500, { error: 'server error' });
    }
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  if (!process.env.API_KEY || process.env.API_KEY.length < 16) { console.error('API_KEY (16+ chars) is required.'); process.exit(1); }
  const port = Number(process.env.PORT) || 3000;
  createApp().listen(port, () => console.log(`md1-publisher listening on :${port}`));
}
