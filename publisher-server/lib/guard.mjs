import crypto from 'node:crypto';

/** In-memory anti-spam guard: blocks identical posts (24h) and caps posts per platform per hour. */
export function createGuard({ perHour = 10, dedupeMs = 24 * 3600 * 1000, now = () => Date.now() } = {}) {
  const seen = new Map();   // key -> time
  const sent = new Map();   // platform -> [times]
  const key = (platform, text) => crypto.createHash('sha256').update(platform + '\n' + text).digest('hex');
  return {
    check(platform, text) {
      const t = now();
      const k = key(platform, text);
      if (seen.has(k) && t - seen.get(k) < dedupeMs) return 'نفس النص نُشر على هذه المنصة خلال آخر 24 ساعة.';
      const arr = (sent.get(platform) || []).filter((x) => t - x < 3600 * 1000);
      sent.set(platform, arr);
      if (arr.length >= perHour) return `تم بلوغ حد النشر (${perHour} منشورات في الساعة) على هذه المنصة.`;
      return null;
    },
    record(platform, text) {
      const t = now();
      seen.set(key(platform, text), t);
      const arr = sent.get(platform) || [];
      arr.push(t);
      sent.set(platform, arr);
    },
  };
}
