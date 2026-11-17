import crypto from 'node:crypto';

export function glen(s) {
  try {
    if (typeof Intl !== 'undefined' && Intl.Segmenter) {
      let n = 0;
      for (const _ of new Intl.Segmenter().segment(s)) n++;
      return n;
    }
  } catch { /* fall through */ }
  return Array.from(s).length;
}

export function safeEqual(a, b) {
  const ha = crypto.createHash('sha256').update(String(a)).digest();
  const hb = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(ha, hb);
}

export function firstLine(text, max = 90) {
  const l = String(text).split('\n').find((x) => x.trim()) || '';
  return l.replace(/^#+\s*/, '').trim().slice(0, max);
}

export function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function toHtmlPage(text) {
  const title = firstLine(text, 80) || 'Post';
  const rtl = /[؀-ۿ]/.test(text);
  const body = text.split(/\n{2,}/).map((p) =>
    '<p>' + esc(p).replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" rel="noopener">$1</a>').replace(/\n/g, '<br>') + '</p>').join('\n');
  return `<!DOCTYPE html>\n<html lang="${rtl ? 'ar' : 'en'}" dir="${rtl ? 'rtl' : 'ltr'}">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>${esc(title)}</title>\n<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem;line-height:1.9}</style>\n</head>\n<body>\n${body}\n</body>\n</html>\n`;
}

/** Collect secret values from env so they can be scrubbed from any error text. */
const SECRET_KEYS = /(TOKEN|SECRET|PASSWORD|API_KEY|WEBHOOK|PASS)/i;
export function scrub(msg, env = process.env) {
  let out = String(msg);
  for (const [k, v] of Object.entries(env)) {
    if (SECRET_KEYS.test(k) && v && v.length >= 6) out = out.split(v).join('***');
  }
  return out.slice(0, 400);
}
