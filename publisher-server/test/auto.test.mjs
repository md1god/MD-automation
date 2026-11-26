import test from 'node:test';
import assert from 'node:assert/strict';
import { pickNext, fallbackText } from '../auto.mjs';
import { glen } from '../lib/util.mjs';

const apps = [{ slug: 'a', h1: 'أ', description: 'وصف', date: '2026-01-01' }, { slug: 'b', h1: 'ب', description: 'وصف', date: '2026-03-01' }, { slug: 'c', h1: 'ج', description: 'وصف', date: '2026-02-01' }];

test('never-promoted pages come first, newest first', () => {
  assert.equal(pickNext(apps, {}).slug, 'b');
  assert.equal(pickNext(apps, { b: '2026-04-01' }).slug, 'c');
});
test('when all promoted, picks the least recently promoted after the cooldown', () => {
  const now = new Date('2026-12-01').getTime();
  assert.equal(pickNext(apps, { a: '2026-01-05', b: '2026-02-01', c: '2026-03-01' }, now).slug, 'a');
});
test('inside the cooldown it still returns something (oldest) rather than nothing', () => {
  const now = new Date('2026-03-02').getTime();
  assert.equal(pickNext(apps, { a: '2026-03-01', b: '2026-02-27', c: '2026-03-01' }, now).slug, 'b');
});
test('fallback text fits the limit and ends with the link', () => {
  const t = fallbackText({ h1: 'أداة', description: 'كلمة '.repeat(200) }, 'https://mdm1.org/apps/x.html');
  assert.ok(glen(t) <= 270); assert.ok(t.endsWith('https://mdm1.org/apps/x.html'));
});
