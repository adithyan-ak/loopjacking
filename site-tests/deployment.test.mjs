import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const html = readFileSync(new URL('../site/index.html', import.meta.url), 'utf8');
function meta(attribute, key) {
  const tags = [...html.matchAll(/<meta\s+([^>]+)>/g)].map(match => match[1]);
  const matching = tags.filter(tag => tag.includes(`${attribute}="${key}"`));
  assert.equal(matching.length, 1, `Exactly one ${key} value is required`);
  return matching[0].match(/content="([^"]+)"/)?.[1];
}

test('canonical and social URLs use the chosen HTTPS domain', () => {
  assert.match(html, /<link rel="canonical" href="https:\/\/loopjacking\.com\/">/);
  assert.equal(meta('property', 'og:url'), 'https://loopjacking.com/');
  assert.equal(meta('property', 'og:type'), 'website');
  assert.equal(meta('name', 'twitter:card'), 'summary_large_image');
});

test('social previews reference the existing qualified figure', () => {
  const image = 'https://loopjacking.com/loopjacking-explained.png';
  assert.equal(meta('property', 'og:image'), image);
  assert.equal(meta('name', 'twitter:image'), image);
  assert.equal(meta('property', 'og:image:width'), '1200');
  assert.equal(meta('property', 'og:image:height'), '630');
  assert.equal(meta('property', 'og:image:type'), 'image/png');
  assert.ok(readFileSync(new URL('../site/loopjacking-explained.png', import.meta.url)).length);
  for (const [attribute, key] of [['property', 'og:image:alt'], ['name', 'twitter:image:alt']]) {
    const alt = meta(attribute, key);
    assert.match(alt, /fictional/);
    assert.match(alt, /cannot authorize directly/);
  }
});

test('social descriptions identify the payment as fictional', () => {
  for (const [attribute, key] of [['property', 'og:description'], ['name', 'twitter:description']]) {
    assert.match(meta(attribute, key), /fictional/);
    assert.match(meta(attribute, key), /human-approval hijacking/);
  }
});
