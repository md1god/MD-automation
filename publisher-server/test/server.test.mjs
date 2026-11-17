import test from 'node:test';
import assert from 'node:assert/strict';
import { createApp } from '../server.mjs';

const KEY = 'k'.repeat(24);
const ENV = { API_KEY: KEY, DISCORD_WEBHOOK_URL: 'https://discord.example/hook' };
async function withServer(fn, discover) {
  const srv = createApp({ env: ENV, discover });
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  try { await fn(base); } finally { await new Promise((r) => srv.close(r)); }
}
const post = (u, body, key = KEY) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(key ? { Authorization: 'Bearer ' + key } : {}) }, body: JSON.stringify(body) });

test('health is public, everything else needs the key', async () => {
  await withServer(async (b) => {
    assert.equal((await fetch(b + '/health')).status, 200);
    assert.equal((await fetch(b + '/platforms')).status, 401);
    assert.equal((await fetch(b + '/platforms', { headers: { Authorization: 'Bearer wrong' } })).status, 401);
    assert.equal((await fetch(b + '/platforms?key=' + KEY)).status, 401, 'query key is only for the oauth start page');
    assert.equal((await fetch(b + '/platforms', { headers: { Authorization: 'Bearer ' + KEY } })).status, 200);
    assert.equal((await fetch(b + '/nope')).status, 404);
  });
});

test('REST publish dry run and validation', async () => {
  await withServer(async (b) => {
    const ok = await (await post(b + '/publish', { text: 'hello', platforms: ['discord'], dry_run: true })).json();
    assert.equal(ok.ok, true);
    assert.equal((await post(b + '/publish', { platforms: ['discord'] })).status, 400);
  });
});

test('MCP: initialize, tools/list, tools/call, notifications, bad key', async () => {
  await withServer(async (b) => {
    const rpc = (body, path = '/mcp', key = KEY) => post(b + path, body, key);
    const init = await (await rpc({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-03-26' } })).json();
    assert.equal(init.result.serverInfo.name, 'md1-publisher');
    assert.equal((await rpc({ jsonrpc: '2.0', method: 'notifications/initialized' })).status, 202);
    const list = await (await rpc({ jsonrpc: '2.0', id: 2, method: 'tools/list' })).json();
    assert.deepEqual(list.result.tools.map((t) => t.name), ['list_platforms', 'publish_post', 'discover_social_links']);
    const call = await (await rpc({ jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'publish_post', arguments: { text: 'hi', platforms: ['discord'], dry_run: true } } })).json();
    assert.equal(JSON.parse(call.result.content[0].text).ok, true);
    // key in the URL path works too (for clients that only accept a URL)
    const viaPath = await (await post(b + '/mcp/' + KEY, { jsonrpc: '2.0', id: 4, method: 'tools/list' }, null)).json();
    assert.equal(viaPath.result.tools.length, 3);
    assert.equal((await post(b + '/mcp/wrong-key-wrong-key-wrong', { jsonrpc: '2.0', id: 5, method: 'tools/list' }, null)).status, 401);
    const unk = await (await rpc({ jsonrpc: '2.0', id: 6, method: 'nope' })).json();
    assert.equal(unk.error.code, -32601);
  });
});

test('discover endpoint uses the injected fetcher and reports errors', async () => {
  await withServer(async (b) => {
    const ok = await (await post(b + '/discover', { url: 'https://example.com' })).json();
    assert.deepEqual(ok.links, []);
    const bad = await post(b + '/discover', { url: 'https://boom.example' });
    assert.equal(bad.status, 400);
  }, async (u) => { if (/boom/.test(u)) throw new Error('blocked address'); return { url: u, links: [] }; });
});
