import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';

// Optional authoring tool only. The website and its tests do not depend on Sharp.
// Keep this in sync with the version documented in this directory's README.
const require = createRequire(import.meta.url);
const sharp = require(process.env.LOOPJACKING_SHARP_MODULE || 'sharp');
assert.equal(sharp.versions.sharp, '0.35.4', 'Use the documented Sharp version for this export');
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const svg = await readFile(new URL('../site/loopjacking-explained.svg', import.meta.url));
const { data: png, info } = await sharp(svg)
  .flatten({ background: '#08090c' })
  .png({ compressionLevel: 9 })
  .toBuffer({ resolveWithObject: true });
assert.equal(info.width, 1200);
assert.equal(info.height, 630);
assert.equal(info.channels, 3);

const record = {
  source: 'site/loopjacking-explained.svg',
  sourceSha256: digest(svg),
  output: 'site/loopjacking-explained.png',
  outputSha256: digest(png),
  width: info.width,
  height: info.height,
  bytes: png.length,
  renderer: {
    sharp: sharp.versions.sharp,
    vips: sharp.versions.vips,
    rsvg: sharp.versions.rsvg,
    platform: process.platform
  }
};
await writeFile(new URL('../site/loopjacking-explained.png', import.meta.url), png);
await writeFile(new URL('./figure-export.json', import.meta.url), `${JSON.stringify(record, null, 2)}\n`);
console.log(`Exported ${info.width}×${info.height} PNG (${png.length} bytes). Inspect the image before committing it.`);
