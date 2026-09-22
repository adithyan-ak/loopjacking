import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const css = readFileSync(new URL('../site/styles.css', import.meta.url), 'utf8');
function color(name) {
  const match = css.match(new RegExp(`--${name}: (#[0-9a-f]{6});`));
  assert.ok(match, `Missing color token ${name}`);
  return match[1];
}
function luminance(hex) {
  const linear = hex.slice(1).match(/../g).map(part => {
    const s = parseInt(part, 16) / 255;
    return s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4;
  });
  return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2];
}
for (const background of ['bg', 'bg-1', 'bg-2', 'panel']) {
  test(`meaningful text tokens reach 4.5:1 on ${background}`, () => {
    for (const foreground of ['ink', 'muted', 'faint', 'amber', 'safe', 'danger', 'cold']) {
      const contrast = (luminance(color(foreground)) + .05) / (luminance(color(background)) + .05);
      assert.ok(contrast >= 4.5, `${foreground}/${background}: ${contrast}`);
    }
  });
}
// This is a palette regression check, not a claim of complete WCAG conformance.
// Browser review still covers opacity, gradients, focus, layout, and semantics.
