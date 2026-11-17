import dns from 'node:dns';
import https from 'node:https';
import net from 'node:net';

export function isPrivateIp(ip) {
  if (net.isIPv4(ip)) {
    const [a, b] = ip.split('.').map(Number);
    return a === 0 || a === 10 || a === 127 || (a === 100 && b >= 64 && b <= 127) || (a === 169 && b === 254) ||
      (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 192 && b === 0) || (a === 198 && (b === 18 || b === 19)) || a >= 224;
  }
  const v = ip.toLowerCase();
  if (v.startsWith('::ffff:')) return isPrivateIp(v.slice(7));
  return v === '::' || v === '::1' || v.startsWith('fc') || v.startsWith('fd') || v.startsWith('fe8') || v.startsWith('fe9') || v.startsWith('fea') || v.startsWith('feb');
}

/** DNS lookup that refuses private/internal addresses. Pinned at connect time, so DNS rebinding cannot bypass it. */
function safeLookup(hostname, opts, cb) {
  dns.lookup(hostname, { ...opts, all: true }, (err, addrs) => {
    if (err) return cb(err);
    const list = Array.isArray(addrs) ? addrs : [{ address: addrs, family: 4 }];
    if (!list.length || list.some((x) => isPrivateIp(x.address))) return cb(new Error('blocked address'));
    if (opts && opts.all) return cb(null, list);
    cb(null, list[0].address, list[0].family);
  });
}

function getOnce(urlStr, { timeoutMs = 8000, maxBytes = 1_500_000 } = {}) {
  return new Promise((resolve, reject) => {
    let u;
    try { u = new URL(urlStr); } catch { return reject(new Error('invalid url')); }
    if (u.protocol !== 'https:' || u.username || u.password || (u.port && u.port !== '443')) return reject(new Error('only plain https URLs on port 443 are allowed'));
    if (net.isIP(u.hostname) && isPrivateIp(u.hostname)) return reject(new Error('blocked address'));
    const req = https.get(u, { lookup: safeLookup, timeout: timeoutMs, headers: { 'User-Agent': 'md1-publisher-discover/1.0', Accept: 'text/html' } }, (res) => {
      if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location) { res.resume(); return resolve({ redirect: new URL(res.headers.location, u).toString() }); }
      if (res.statusCode !== 200) { res.resume(); return reject(new Error('HTTP ' + res.statusCode)); }
      let size = 0; const chunks = [];
      res.on('data', (c) => { size += c.length; if (size > maxBytes) { req.destroy(new Error('page too large')); } else chunks.push(c); });
      res.on('end', () => resolve({ html: Buffer.concat(chunks).toString('utf8') }));
      res.on('error', reject);
    });
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', reject);
  });
}

export async function fetchPage(url) {
  let cur = url;
  for (let i = 0; i < 4; i++) {
    const r = await getOnce(cur);
    if (r.html !== undefined) return r.html;
    cur = r.redirect;
  }
  throw new Error('too many redirects');
}

const RULES = [
  ['x', /^(?:www\.|mobile\.)?(?:x|twitter)\.com\/(?!intent|share|home|i\/|search|hashtag)@?([A-Za-z0-9_]{1,15})\/?$/i],
  ['linkedin', /^(?:[a-z]{2,3}\.)?linkedin\.com\/((?:in|company|school)\/[^/?#]+)\/?$/i],
  ['facebook', /^(?:www\.|m\.)?facebook\.com\/(?!sharer|share|dialog|plugins|tr\b)([A-Za-z0-9.\-]+(?:\/[A-Za-z0-9.\-]+)?)\/?$/i],
  ['instagram', /^(?:www\.)?instagram\.com\/(?!p\/|reel\/|explore)([A-Za-z0-9._]+)\/?$/i],
  ['youtube', /^(?:www\.|m\.)?youtube\.com\/((?:@[^/?#]+|channel\/[^/?#]+|c\/[^/?#]+|user\/[^/?#]+))\/?$/i],
  ['tiktok', /^(?:www\.)?tiktok\.com\/(@[A-Za-z0-9._]+)\/?$/i],
  ['telegram', /^(?:t|telegram)\.me\/(?!share)([A-Za-z0-9_]{4,})\/?$/i],
  ['github', /^(?:www\.)?github\.com\/([A-Za-z0-9-]+)\/?$/i],
  ['bluesky', /^bsky\.app\/profile\/([^/?#]+)\/?$/i],
  ['threads', /^(?:www\.)?threads\.(?:net|com)\/(@[A-Za-z0-9._]+)\/?$/i],
  ['pinterest', /^(?:[a-z]{2}\.)?pinterest\.com\/([A-Za-z0-9_]+)\/?$/i],
  ['reddit', /^(?:www\.)?reddit\.com\/((?:u|user|r)\/[A-Za-z0-9_-]+)\/?$/i],
  ['discord', /^discord\.(?:gg|com\/invite)\/([A-Za-z0-9-]+)\/?$/i],
];

export function extractSocialLinks(html, baseUrl = 'https://example.com/') {
  const found = new Map();
  const add = (raw) => {
    let u;
    try { u = new URL(raw.replace(/&amp;/g, '&'), baseUrl); } catch { return; }
    if (!/^https?:$/.test(u.protocol)) return;
    const key = u.hostname.replace(/^www\./, '') + u.pathname;
    for (const [platform, re] of RULES) {
      const m = key.match(re) || (u.hostname + u.pathname).match(re);
      if (m) { const handle = m[1]; const id = platform + ':' + handle.toLowerCase(); if (!found.has(id)) found.set(id, { platform, handle, url: u.origin + u.pathname.replace(/\/$/, '') }); return; }
    }
  };
  for (const m of html.matchAll(/<(?:a|link)\b[^>]*?\bhref\s*=\s*["']([^"']+)["']/gi)) add(m[1]);
  for (const m of html.matchAll(/<script[^>]*application\/ld\+json[^>]*>([\s\S]*?)<\/script>/gi)) {
    try {
      const walk = (n) => { if (Array.isArray(n)) n.forEach(walk); else if (n && typeof n === 'object') { if (n.sameAs) [].concat(n.sameAs).forEach((x) => typeof x === 'string' && add(x)); Object.values(n).forEach(walk); } };
      walk(JSON.parse(m[1]));
    } catch { /* ignore bad json-ld */ }
  }
  return [...found.values()];
}

export async function discoverSocialLinks(url) {
  const html = await fetchPage(url);
  return { url, links: extractSocialLinks(html, url) };
}
