import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const svg = readFileSync(new URL('../site/loopjacking-explained.svg', import.meta.url));
const png = readFileSync(new URL('../site/loopjacking-explained.png', import.meta.url));
const record = JSON.parse(readFileSync(new URL('../site-tools/figure-export.json', import.meta.url), 'utf8'));
const digest = bytes => createHash('sha256').update(bytes).digest('hex');

// Integrity checks only. Hashes do not prove readability, correct rasterization,
// platform preview support, or that a human has inspected the exported image.
test('the figure export record matches the current SVG and PNG bytes', () => {
  assert.equal(record.source, 'site/loopjacking-explained.svg');
  assert.equal(record.output, 'site/loopjacking-explained.png');
  assert.equal(record.sourceSha256, digest(svg), 'SVG changed; regenerate and inspect the PNG');
  assert.equal(record.outputSha256, digest(png), 'PNG changed; regenerate and inspect the export record');
  assert.equal(record.bytes, png.length);
});

test('the downloadable PNG has the expected opaque 1200 by 630 RGB header', () => {
  assert.deepEqual(png.subarray(0, 8), Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  assert.equal(png.readUInt32BE(8), 13, 'IHDR has its standard length');
  assert.equal(png.toString('ascii', 12, 16), 'IHDR');
  assert.equal(png.readUInt32BE(16), 1200);
  assert.equal(png.readUInt32BE(20), 630);
  assert.equal(png[24], 8, '8-bit samples');
  assert.equal(png[25], 2, 'RGB without transparency');
  assert.equal(record.width, 1200);
  assert.equal(record.height, 630);
});
