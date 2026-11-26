// CLI entry for GitHub Actions: publishes using the same adapters as the server. No hosting needed.
import fs from 'node:fs';
import { publish } from './lib/publisher.mjs';

const env = process.env;
const platforms = String(env.PLATFORMS || '').split(',').map((s) => s.trim()).filter(Boolean);
const options = {};
if (env.SUBREDDIT) options.subreddit = env.SUBREDDIT;
if (env.TAGS) options.tags = String(env.TAGS).split(',').map((s) => s.trim()).filter(Boolean);

const out = await publish({
  text: env.POST_TEXT || '', platforms, link: env.POST_LINK || undefined, title: env.POST_TITLE || undefined,
  options, dry_run: String(env.DRY_RUN) === 'true',
}, { env });

const lines = out.results.map((r) => `${r.ok ? 'OK ' : 'ERR'} ${r.platform}${r.url ? ' ' + r.url : ''}${r.error ? ' ' + r.error : ''}${r.dry_run ? ' (dry run)' : ''}`);
console.log(lines.join('\n') || out.error);
if (env.GITHUB_STEP_SUMMARY) fs.appendFileSync(env.GITHUB_STEP_SUMMARY, '### Publish results\n\n```\n' + (lines.join('\n') || out.error) + '\n```\n');
process.exit(out.ok ? 0 : 1);
