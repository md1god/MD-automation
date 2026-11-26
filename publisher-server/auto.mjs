// Autonomous promoter: picks the next page of the site by itself, writes the post by itself (free GitHub Models,
// template fallback), and publishes to YOUR OWN configured channels. No comments on other people's content.
import fs from 'node:fs';
import { publish, listPlatforms } from './lib/publisher.mjs';
import { glen } from './lib/util.mjs';

const env = process.env;
const SITE = (env.SITE_URL || 'https://mdm1.org').replace(/\/+$/, '');
const STATE = new URL('./state/promoted.json', import.meta.url);
const COOLDOWN_DAYS = Number(env.PROMO_COOLDOWN_DAYS) || 45;
const SAFE_DEFAULT = ['bluesky', 'mastodon', 'telegram', 'discord', 'linkedin', 'facebook'];
const MAX_TEXT = 270; // fits Bluesky (300) and X (280); URL counted in full

const note = (m) => console.log(m);
const readState = () => { try { return JSON.parse(fs.readFileSync(STATE, 'utf8')); } catch { return {}; } };

export function pickNext(apps, state, now = Date.now()) {
  const days = (d) => (now - new Date(d).getTime()) / 86400000;
  const fresh = apps.filter((a) => !state[a.slug]);
  if (fresh.length) return fresh.sort((a, b) => String(b.date).localeCompare(String(a.date)))[0];
  const cooled = apps.filter((a) => days(state[a.slug]) >= COOLDOWN_DAYS);
  const pool = cooled.length ? cooled : apps;
  return pool.sort((a, b) => new Date(state[a.slug]) - new Date(state[b.slug]))[0];
}

export function fallbackText(app, url) {
  const head = String(app.h1 || app.title || '').trim();
  let body = String(app.description || '').trim();
  const fixed = `${head}\n\n`;
  const tail = `\n\n${url}`;
  const room = MAX_TEXT - glen(fixed) - glen(tail);
  if (glen(body) > room) body = Array.from(body).slice(0, Math.max(0, room - 1)).join('').trimEnd() + '…';
  return fixed + body + tail;
}

async function llmText(app, url) {
  if (!env.GITHUB_TOKEN || env.PROMO_NO_LLM === 'true') return null;
  const sys = 'You write short honest social posts for a free web tool made by the account owner. Output only the post text. No hype, no emojis spam, no invented facts or numbers, no claims beyond the description.';
  const usr = `Write ONE post in Arabic (max 200 characters excluding the link) announcing this free tool as our own project.\nName: ${app.h1}\nDescription: ${app.description}\nEnd the post with this exact link on its own line: ${url}`;
  for (const model of ['openai/gpt-4.1-mini', 'openai/gpt-4o-mini']) {
    try {
      const r = await fetch('https://models.github.ai/inference/chat/completions', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.GITHUB_TOKEN}` }, body: JSON.stringify({ model, messages: [{ role: 'system', content: sys }, { role: 'user', content: usr }], temperature: 0.7, max_tokens: 300 }) });
      if (!r.ok) continue;
      const j = await r.json();
      let t = String(j.choices?.[0]?.message?.content || '').trim().replace(/^["«“]+|["»”]+$/g, '');
      const n = (t.match(/https?:\/\/\S+/g) || []);
      if (n.length !== 1 || n[0] !== url || glen(t) > MAX_TEXT || /(^|\s)#{1}\S+(\s+#\S+){3,}/.test(t)) continue; // exactly our link, fits, no hashtag spam
      return t;
    } catch { /* try next model */ }
  }
  return null;
}

async function main() {
  const configured = listPlatforms(env).filter((p) => p.configured).map((p) => p.id);
  const wanted = (env.PROMO_PLATFORMS ? env.PROMO_PLATFORMS.split(',').map((s) => s.trim()) : SAFE_DEFAULT).filter(Boolean);
  const platforms = wanted.filter((p) => configured.includes(p));
  if (!platforms.length) { note('No platform is configured yet. Add at least one secret (see publisher-server/README.md). Nothing to do.'); return 0; }

  const res = await fetch(`${SITE}/data/apps.json`, { headers: { 'User-Agent': 'md1-auto-promote' } });
  if (!res.ok) { note(`::error::could not read ${SITE}/data/apps.json (${res.status})`); return 1; }
  const apps = (await res.json()).apps || [];
  if (!apps.length) { note('::error::no apps found'); return 1; }

  const state = readState();
  const app = pickNext(apps, state);
  const url = `${SITE}/apps/${app.slug}.html`;
  const text = (await llmText(app, url)) || fallbackText(app, url);
  note(`Picked: ${app.slug}\nPlatforms: ${platforms.join(', ')}\n---\n${text}\n---`);

  const out = await publish({ text, platforms, link: url, dry_run: String(env.DRY_RUN) === 'true' }, { env });
  for (const r of out.results) note(`${r.ok ? 'OK ' : 'ERR'} ${r.platform}${r.url ? ' ' + r.url : ''}${r.error ? ' ' + r.error : ''}${r.dry_run ? ' (dry run)' : ''}`);
  if (env.GITHUB_STEP_SUMMARY) fs.appendFileSync(env.GITHUB_STEP_SUMMARY, `### Auto promote\n\n${app.slug}\n\n\`\`\`\n${text}\n\`\`\`\n`);
  if (String(env.DRY_RUN) !== 'true' && out.results.some((r) => r.ok)) {
    state[app.slug] = new Date().toISOString().slice(0, 10);
    fs.writeFileSync(STATE, JSON.stringify(state, null, 1) + '\n');
  }
  return out.results.some((r) => r.ok) || String(env.DRY_RUN) === 'true' ? 0 : 1;
}

if (import.meta.url === `file://${process.argv[1]}`) process.exit(await main());
