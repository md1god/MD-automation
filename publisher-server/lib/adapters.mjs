import { firstLine, toHtmlPage } from './util.mjs';

const JSON_H = { 'Content-Type': 'application/json' };

async function call(url, opts = {}) {
  const r = await fetch(url, opts);
  const t = await r.text();
  let j = null;
  try { j = JSON.parse(t); } catch { /* not json */ }
  return { r, j, t };
}
const fail = (what, { r, j, t }) => {
  const m = j && (j.message || j.error_description || (typeof j.error === 'string' ? j.error : j.error && j.error.message) || j.description || j.detail);
  throw new Error(`${what}: ${r.status}${m ? ' ' + String(m).slice(0, 200) : t ? ' ' + t.slice(0, 120) : ''}`);
};

export const ADAPTERS = {
  bluesky: {
    name: 'Bluesky', limit: 300, env: ['BSKY_HANDLE', 'BSKY_APP_PASSWORD'],
    async post({ text }, env) {
      const svc = (env.BSKY_SERVICE || 'https://bsky.social').replace(/\/+$/, '');
      const s = await call(`${svc}/xrpc/com.atproto.server.createSession`, { method: 'POST', headers: JSON_H, body: JSON.stringify({ identifier: env.BSKY_HANDLE.replace(/^@/, ''), password: env.BSKY_APP_PASSWORD }) });
      if (!s.r.ok) fail('Bluesky login', s);
      const enc = new TextEncoder(); const facets = []; const re = /https?:\/\/[^\s]+/g; let m;
      while ((m = re.exec(text))) {
        const a = enc.encode(text.slice(0, m.index)).length;
        facets.push({ index: { byteStart: a, byteEnd: a + enc.encode(m[0]).length }, features: [{ $type: 'app.bsky.richtext.facet#link', uri: m[0] }] });
      }
      const record = { $type: 'app.bsky.feed.post', text, createdAt: new Date().toISOString() };
      if (facets.length) record.facets = facets;
      const c = await call(`${svc}/xrpc/com.atproto.repo.createRecord`, { method: 'POST', headers: { ...JSON_H, Authorization: `Bearer ${s.j.accessJwt}` }, body: JSON.stringify({ repo: s.j.did, collection: 'app.bsky.feed.post', record }) });
      if (!c.r.ok) fail('Bluesky post', c);
      const rkey = String(c.j.uri || '').split('/').pop();
      return { url: `https://bsky.app/profile/${s.j.did}/post/${rkey}` };
    },
  },
  mastodon: {
    name: 'Mastodon', limit: 500, env: ['MASTODON_HOST', 'MASTODON_TOKEN'],
    async post({ text }, env) {
      let host = env.MASTODON_HOST.replace(/\/+$/, ''); if (!/^https:\/\//i.test(host)) host = 'https://' + host;
      const c = await call(`${host}/api/v1/statuses`, { method: 'POST', headers: { ...JSON_H, Authorization: `Bearer ${env.MASTODON_TOKEN}` }, body: JSON.stringify({ status: text, visibility: 'public' }) });
      if (!c.r.ok) fail('Mastodon', c);
      return { url: c.j && c.j.url };
    },
  },
  telegram: {
    name: 'Telegram', limit: 4096, env: ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID'],
    async post({ text }, env) {
      const c = await call(`https://api.telegram.org/bot${encodeURIComponent(env.TELEGRAM_BOT_TOKEN)}/sendMessage`, { method: 'POST', headers: JSON_H, body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text }) });
      if (!c.j || !c.j.ok) throw new Error('Telegram: ' + ((c.j && c.j.description) || c.r.status));
      const chat = String(env.TELEGRAM_CHAT_ID);
      return { url: chat.startsWith('@') ? `https://t.me/${chat.slice(1)}/${c.j.result.message_id}` : undefined };
    },
  },
  discord: {
    name: 'Discord', limit: 2000, env: ['DISCORD_WEBHOOK_URL'],
    async post({ text }, env) {
      const u = env.DISCORD_WEBHOOK_URL + (env.DISCORD_WEBHOOK_URL.includes('?') ? '&' : '?') + 'wait=true';
      const c = await call(u, { method: 'POST', headers: JSON_H, body: JSON.stringify({ content: text }) });
      if (!c.r.ok) fail('Discord', c);
      return {};
    },
  },
  linkedin: {
    name: 'LinkedIn', limit: 3000, env: ['LINKEDIN_ACCESS_TOKEN', 'LINKEDIN_AUTHOR_URN'],
    async post({ text }, env) {
      const body = { author: env.LINKEDIN_AUTHOR_URN, commentary: text, visibility: 'PUBLIC', distribution: { feedDistribution: 'MAIN_FEED', targetEntities: [], thirdPartyDistributionChannels: [] }, lifecycleState: 'PUBLISHED', isReshareDisabledByAuthor: false };
      const c = await call('https://api.linkedin.com/rest/posts', { method: 'POST', headers: { ...JSON_H, Authorization: `Bearer ${env.LINKEDIN_ACCESS_TOKEN}`, 'LinkedIn-Version': env.LINKEDIN_API_VERSION || '202511', 'X-Restli-Protocol-Version': '2.0.0' }, body: JSON.stringify(body) });
      if (!c.r.ok) fail('LinkedIn', c);
      const id = c.r.headers.get('x-restli-id');
      return { url: id ? `https://www.linkedin.com/feed/update/${id}/` : undefined };
    },
  },
  x: {
    name: 'X', limit: 280, env: ['X_ACCESS_TOKEN'],
    async post({ text }, env) {
      const c = await call('https://api.x.com/2/tweets', { method: 'POST', headers: { ...JSON_H, Authorization: `Bearer ${env.X_ACCESS_TOKEN}` }, body: JSON.stringify({ text }) });
      if (!c.r.ok) fail('X', c);
      return { url: c.j && c.j.data ? `https://x.com/i/status/${c.j.data.id}` : undefined };
    },
  },
  facebook: {
    name: 'Facebook Page', limit: 5000, env: ['FACEBOOK_PAGE_ID', 'FACEBOOK_PAGE_TOKEN'],
    async post({ text, link }, env) {
      const f = new URLSearchParams({ message: text, access_token: env.FACEBOOK_PAGE_TOKEN }); if (link) f.set('link', link);
      const c = await call(`https://graph.facebook.com/v21.0/${encodeURIComponent(env.FACEBOOK_PAGE_ID)}/feed`, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: f });
      if (!c.r.ok) fail('Facebook', c);
      return { url: c.j && c.j.id ? `https://www.facebook.com/${c.j.id}` : undefined };
    },
  },
  reddit: {
    name: 'Reddit', limit: 3000, env: ['REDDIT_CLIENT_ID', 'REDDIT_CLIENT_SECRET', 'REDDIT_USERNAME', 'REDDIT_PASSWORD'],
    async post({ text, title, options }, env) {
      const ua = `md1-publisher/1.0 by ${env.REDDIT_USERNAME}`;
      const sr = (options && options.subreddit) || env.REDDIT_SUBREDDIT || `u_${env.REDDIT_USERNAME}`;
      const t = await call('https://www.reddit.com/api/v1/access_token', { method: 'POST', headers: { Authorization: 'Basic ' + Buffer.from(`${env.REDDIT_CLIENT_ID}:${env.REDDIT_CLIENT_SECRET}`).toString('base64'), 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': ua }, body: new URLSearchParams({ grant_type: 'password', username: env.REDDIT_USERNAME, password: env.REDDIT_PASSWORD }) });
      if (!t.r.ok || !t.j || !t.j.access_token) fail('Reddit login', t);
      const body = (title ? text : text.split('\n').slice(1).join('\n').trim());
      const f = new URLSearchParams({ api_type: 'json', kind: 'self', sr, title: (title || firstLine(text, 300)).slice(0, 300), text: body });
      const c = await call('https://oauth.reddit.com/api/submit', { method: 'POST', headers: { Authorization: `Bearer ${t.j.access_token}`, 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': ua }, body: f });
      const errs = c.j && c.j.json && c.j.json.errors;
      if (!c.r.ok || (errs && errs.length)) throw new Error('Reddit: ' + (errs && errs.length ? JSON.stringify(errs).slice(0, 200) : c.r.status));
      return { url: c.j && c.j.json && c.j.json.data && c.j.json.data.url };
    },
  },
  devto: {
    name: 'DEV.to', limit: 100000, env: ['DEVTO_API_KEY'],
    async post({ text, title, options }, env) {
      const tags = ((options && options.tags) || []).slice(0, 4);
      const article = { title: title || firstLine(text, 120), body_markdown: title ? text : text.split('\n').slice(1).join('\n').trim() || text, published: true };
      if (tags.length) article.tags = tags;
      const c = await call('https://dev.to/api/articles', { method: 'POST', headers: { ...JSON_H, 'api-key': env.DEVTO_API_KEY }, body: JSON.stringify({ article }) });
      if (!c.r.ok) fail('DEV.to', c);
      return { url: c.j && c.j.url };
    },
  },
  wordpress: {
    name: 'WordPress', limit: 100000, env: ['WORDPRESS_URL', 'WORDPRESS_USER', 'WORDPRESS_APP_PASSWORD'],
    async post({ text, title }, env) {
      const base = env.WORDPRESS_URL.replace(/\/+$/, '');
      const html = text.split(/\n{2,}/).map((p) => '<p>' + p.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/\n/g, '<br>') + '</p>').join('\n');
      const c = await call(`${base}/wp-json/wp/v2/posts`, { method: 'POST', headers: { ...JSON_H, Authorization: 'Basic ' + Buffer.from(`${env.WORDPRESS_USER}:${env.WORDPRESS_APP_PASSWORD}`).toString('base64') }, body: JSON.stringify({ title: title || firstLine(text, 120), content: html, status: 'publish' }) });
      if (!c.r.ok) fail('WordPress', c);
      return { url: c.j && c.j.link };
    },
  },
  github: {
    name: 'GitHub Pages', limit: 100000, env: ['PUBLISH_GH_TOKEN', 'PUBLISH_GH_REPO'],
    async post({ text }, env) {
      const repo = env.PUBLISH_GH_REPO;
      if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) throw new Error('PUBLISH_GH_REPO must be owner/repo');
      const d = new Date(); const p = (n) => String(n).padStart(2, '0');
      const name = `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}-${p(d.getUTCHours())}${p(d.getUTCMinutes())}${p(d.getUTCSeconds())}.html`;
      const dir = (env.PUBLISH_GH_DIR || 'posts').replace(/^\/+|\/+$/g, '');
      const body = { message: `Publish ${name}`, content: Buffer.from(toHtmlPage(text), 'utf8').toString('base64') };
      if (env.PUBLISH_GH_BRANCH) body.branch = env.PUBLISH_GH_BRANCH;
      const c = await call(`https://api.github.com/repos/${repo}/contents/${dir}/${name}`, { method: 'PUT', headers: { ...JSON_H, Accept: 'application/vnd.github+json', Authorization: `Bearer ${env.PUBLISH_GH_TOKEN}`, 'User-Agent': 'md1-publisher' }, body: JSON.stringify(body) });
      if (!c.r.ok) fail('GitHub', c);
      return { url: c.j && c.j.content && c.j.content.html_url };
    },
  },
  webhook: {
    name: 'Webhook', limit: 100000, env: ['WEBHOOK_URL'],
    async post({ text, title, link }, env) {
      const c = await call(env.WEBHOOK_URL, { method: 'POST', headers: JSON_H, body: JSON.stringify({ text, title, link, createdAt: new Date().toISOString(), source: 'md1-publisher' }) });
      if (!c.r.ok) fail('Webhook', c);
      return {};
    },
  },
};

export const isConfigured = (id, env) => ADAPTERS[id].env.every((k) => env[k]);
