import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const root = new URL('../site/fonts/', import.meta.url);
const html = readFileSync(new URL('../site/index.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('fonts.css', root), 'utf8');
const manifest = JSON.parse(readFileSync(new URL('manifest.json', root), 'utf8'));
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const faces = [...css.matchAll(/@font-face\s*\{([^}]+)\}/g)].map(match => match[1]);

// Static integrity only: these checks do not measure rendered glyphs, network
// performance, or availability of a deployed site. Browser checks remain needed.
test('the page loads its font stylesheet locally without external font connections', () => {
  assert.match(html, /<link rel="stylesheet" href="\.\/fonts\/fonts\.css">/);
  assert.doesNotMatch(html, /fonts\.(?:googleapis|gstatic)\.com/);
  assert.doesNotMatch(css, /@import|https?:\/\//i);
  assert.equal(digest(Buffer.from(css)), manifest.stylesheetSha256);
});

test('the bundled faces retain the three requested families, weights, and swap behavior', () => {
  assert.equal(faces.length, 58);
  assert.equal(manifest.fontFaceCount, faces.length);
  const weights = new Map();
  for (const face of faces) {
    const family = face.match(/font-family:\s*'([^']+)'/)[1];
    const weight = Number(face.match(/font-weight:\s*(\d+)/)[1]);
    if (!weights.has(family)) weights.set(family, new Set());
    weights.get(family).add(weight);
    assert.match(face, /font-style:\s*normal;/);
    assert.match(face, /font-display:\s*swap;/);
    assert.match(face, /unicode-range:\s*U\+/);
  }
  assert.deepEqual(Object.fromEntries([...weights].map(([family, values]) => [family, [...values].sort((a, b) => a - b)])), {
    'Chakra Petch': [400, 500, 600, 700],
    'IBM Plex Sans': [300, 400, 500, 600],
    'JetBrains Mono': [400, 500, 700]
  });
});

test('every referenced WOFF2 file matches its recorded source bytes', () => {
  const paths = new Set([...css.matchAll(/url\(\.\/([^)]*)\)/g)].map(match => match[1]));
  assert.equal(paths.size, 28);
  assert.equal(manifest.files.length, paths.size);
  assert.deepEqual(paths, new Set(manifest.files.map(file => file.path)));
  for (const file of manifest.files) {
    assert.match(file.path, /^assets\/[a-f0-9]{20}\.woff2$/);
    assert.equal(new URL(file.source).origin, 'https://fonts.gstatic.com');
    const bytes = readFileSync(new URL(file.path, root));
    assert.equal(bytes.toString('ascii', 0, 4), 'wOF2');
    assert.equal(bytes.length, file.bytes);
    assert.equal(digest(bytes), file.sha256);
  }
});

test('all three complete copyright and license notices remain byte-exact', () => {
  const expected = ['chakra-petch-OFL.txt', 'ibm-plex-sans-OFL.txt', 'jetbrains-mono-OFL.txt'];
  assert.deepEqual(manifest.licenses.map(license => license.path), expected);
  for (const license of manifest.licenses) {
    const bytes = readFileSync(new URL(license.path, root));
    assert.equal(digest(bytes), license.sha256);
    assert.match(bytes.toString('utf8'), /Copyright.*(?:Authors|IBM Corp)/);
    assert.match(bytes.toString('utf8'), /SIL OPEN FONT LICENSE Version 1\.1/);
  }
});
