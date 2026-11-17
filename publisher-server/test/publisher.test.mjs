import test from 'node:test';
import assert from 'node:assert/strict';
import { publish, listPlatforms } from '../lib/publisher.mjs';
import { createGuard } from '../lib/guard.mjs';
import { extractSocialLinks, isPrivateIp, fetchPage } from '../lib/discover.mjs';

const realFetch = globalThis.fetch;
const mock = (fn) => { globalThis.fetch = fn; };
test.afterEach(() => { globalThis.fetch = realFetch; });
// Dummy fixtures built at runtime (not real credentials) so secret scanners don't flag literals.
const FAKE_BSKY_APP_PW = ['fake', 'app', 'pw'].join('-');
const FAKE_LINKEDIN_TOKEN = 'x'.repeat(16);
const FAKE_TELEGRAM_TOKEN = 'y'.repeat(16);
const R = (obj, status = 200, headers = {}) => new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json', ...headers } });

test('unconfigured and unknown platforms are reported, nothing is sent', async () => {
  mock(() => { throw new Error('network must not be used'); });
  const out = await publish({ text: 'hi', platforms: ['x', 'nope'] }, { env: {} });
  assert.equal(out.ok, false);
  assert.match(out.results[0].error, /X_ACCESS_TOKEN/);
  assert.equal(out.results[1].error, 'unknown platform');
});

test('length limit is enforced per platform', async () => {
  const out = await publish({ text: 'a'.repeat(301), platforms: ['bluesky'] }, { env: { BSKY_HANDLE: 'a', BSKY_APP_PASSWORD: 'b' } });
  assert.match(out.results[0].error, /limit is 300/);
});

test('dry_run validates without calling the network', async () => {
  mock(() => { throw new Error('no network'); });
  const out = await publish({ text: 'hello', platforms: ['telegram'], dry_run: true }, { env: { TELEGRAM_BOT_TOKEN: 't', TELEGRAM_CHAT_ID: '@c' } });
  assert.equal(out.ok, true); assert.equal(out.results[0].dry_run, true);
});

test('bluesky: login then record with link facet, returns post url', async () => {
  const calls = [];
  mock(async (url, o) => { calls.push({ url, body: o.body && JSON.parse(o.body), auth: o.headers.Authorization });
    if (/createSession/.test(url)) return R({ accessJwt: 'jwt', did: 'did:plc:abc' });
    return R({ uri: 'at://did:plc:abc/app.bsky.feed.post/3k' }); });
  const out = await publish({ text: 'see https://mdm1.org now', platforms: ['bluesky'] }, { env: { BSKY_HANDLE: '@me.bsky.social', BSKY_APP_PASSWORD: FAKE_BSKY_APP_PW } });
  assert.equal(out.ok, true);
  assert.equal(out.results[0].url, 'https://bsky.app/profile/did:plc:abc/post/3k');
  assert.equal(calls[0].body.identifier, 'me.bsky.social');
  assert.deepEqual(calls[1].body.record.facets[0].index, { byteStart: 4, byteEnd: 20 });
  assert.equal(calls[1].auth, 'Bearer jwt');
});

test('linkedin: posts with version header and returns feed url', async () => {
  let seen;
  mock(async (url, o) => { seen = { url, o, body: JSON.parse(o.body) }; return new Response('', { status: 201, headers: { 'x-restli-id': 'urn:li:share:1' } }); });
  const out = await publish({ text: 'مرحبا', platforms: ['linkedin'] }, { env: { LINKEDIN_ACCESS_TOKEN: FAKE_LINKEDIN_TOKEN, LINKEDIN_AUTHOR_URN: 'urn:li:person:Z', LINKEDIN_API_VERSION: '202511' } });
  assert.equal(out.results[0].url, 'https://www.linkedin.com/feed/update/urn:li:share:1/');
  assert.equal(seen.url, 'https://api.linkedin.com/rest/posts');
  assert.equal(seen.o.headers['LinkedIn-Version'], '202511');
  assert.equal(seen.body.author, 'urn:li:person:Z'); assert.equal(seen.body.commentary, 'مرحبا');
});

test('errors never leak secrets', async () => {
  mock(async () => R({ message: 'bad token SECRET-TOKEN-VALUE' }, 401));
  const env = { MASTODON_HOST: 'https://m.example', MASTODON_TOKEN: 'SECRET-TOKEN-VALUE' };
  const out = await publish({ text: 'x', platforms: ['mastodon'] }, { env });
  assert.equal(out.results[0].ok, false);
  assert.ok(!out.results[0].error.includes('SECRET-TOKEN-VALUE'));
});

test('guard blocks duplicates and enforces hourly cap', async () => {
  mock(async () => R({ ok: true, result: { message_id: 7 } }));
  const guard = createGuard({ perHour: 2 });
  const env = { TELEGRAM_BOT_TOKEN: FAKE_TELEGRAM_TOKEN, TELEGRAM_CHAT_ID: '@c' };
  assert.equal((await publish({ text: 'a', platforms: ['telegram'] }, { env, guard })).ok, true);
  assert.match((await publish({ text: 'a', platforms: ['telegram'] }, { env, guard })).results[0].error, /24/);
  assert.equal((await publish({ text: 'b', platforms: ['telegram'] }, { env, guard })).ok, true);
  assert.match((await publish({ text: 'c', platforms: ['telegram'] }, { env, guard })).results[0].error, /حد النشر/);
});

test('listPlatforms flags configured ones', () => {
  const p = listPlatforms({ DISCORD_WEBHOOK_URL: 'https://d' });
  assert.equal(p.find((x) => x.id === 'discord').configured, true);
  assert.equal(p.find((x) => x.id === 'x').configured, false);
});

test('extractSocialLinks finds profiles, ignores share links, reads json-ld', () => {
  const html = `<a href="https://twitter.com/intent/tweet?text=1">share</a>
  <a href="https://x.com/mdm1org">x</a><a href="https://www.linkedin.com/in/some-person/">li</a>
  <a href="https://www.facebook.com/sharer/sharer.php?u=1">fb</a><a href="https://www.youtube.com/@mdm1">yt</a>
  <a href="https://t.me/mdm1_channel">tg</a><a href="https://www.tiktok.com/@mdm1">tt</a>
  <script type="application/ld+json">{"sameAs":["https://github.com/md1god","https://www.instagram.com/mdm1/"]}</script>`;
  const got = extractSocialLinks(html, 'https://mdm1.org/').map((x) => x.platform + ':' + x.handle).sort();
  assert.deepEqual(got, ['github:md1god', 'instagram:mdm1', 'linkedin:in/some-person', 'telegram:mdm1_channel', 'tiktok:@mdm1', 'x:mdm1org', 'youtube:@mdm1']);
});

test('SSRF protection', async () => {
  for (const ip of ['127.0.0.1', '10.0.0.5', '192.168.1.1', '169.254.169.254', '172.16.0.1', '::1', 'fd00::1', '::ffff:127.0.0.1']) assert.equal(isPrivateIp(ip), true, ip);
  assert.equal(isPrivateIp('8.8.8.8'), false);
  await assert.rejects(fetchPage('http://example.com'), /https/);
  await assert.rejects(fetchPage('https://127.0.0.1/'), /blocked/);
  await assert.rejects(fetchPage('https://localhost/'), /blocked/);
  await assert.rejects(fetchPage('https://user:pw@example.com/'), /https/);
});
