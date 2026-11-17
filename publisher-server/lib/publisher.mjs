import { ADAPTERS, isConfigured } from './adapters.mjs';
import { glen, scrub } from './util.mjs';

export function listPlatforms(env = process.env) {
  return Object.entries(ADAPTERS).map(([id, a]) => ({ id, name: a.name, limit: a.limit, configured: isConfigured(id, env), needs: a.env }));
}

/** Publish `text` to each requested platform. Never throws; returns one result per platform. */
export async function publish(args, { env = process.env, guard } = {}) {
  const text = String(args.text || '').trim();
  const link = args.link ? String(args.link).trim() : undefined;
  const ids = Array.isArray(args.platforms) ? [...new Set(args.platforms.map(String))] : [];
  const dry = args.dry_run === true;
  if (!text) return { ok: false, error: 'text is required', results: [] };
  if (!ids.length) return { ok: false, error: 'platforms is required (see list_platforms)', results: [] };
  if (ids.length > 15) return { ok: false, error: 'too many platforms', results: [] };

  const results = await Promise.all(ids.map(async (id) => {
    const a = ADAPTERS[id];
    if (!a) return { platform: id, ok: false, error: 'unknown platform' };
    if (!isConfigured(id, env)) return { platform: id, ok: false, error: 'not configured. Missing env: ' + a.env.filter((k) => !env[k]).join(', ') };
    const n = glen(text);
    if (n > a.limit) return { platform: id, ok: false, error: `text is ${n} chars, limit is ${a.limit}` };
    if (dry) return { platform: id, ok: true, dry_run: true, message: `would post ${n} chars` };
    const blocked = guard && guard.check(id, text);
    if (blocked) return { platform: id, ok: false, error: blocked };
    try {
      const out = await a.post({ text, link, title: args.title, options: args.options }, env);
      if (guard) guard.record(id, text);
      return { platform: id, ok: true, ...out };
    } catch (e) {
      return { platform: id, ok: false, error: scrub(e && e.message ? e.message : e, env) };
    }
  }));
  return { ok: results.every((r) => r.ok), results };
}
