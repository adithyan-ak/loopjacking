import { test } from 'node:test';
import assert from 'node:assert/strict';
import { lstatSync, readdirSync, readFileSync } from 'node:fs';
import { extname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// Local source integrity for the known static site, not a crawler or HTML/JS
// conformance check. No URL is fetched. Explicit schemes and protocol-relative
// URLs are excluded; only literal module imports and CSS url() values are read.
// Each local path component is checked for exact spelling and with lstat before
// the target is read, including on case-insensitive development filesystems.
const siteRoot = resolve(fileURLToPath(new URL('../site/', import.meta.url)));
assert.equal(lstatSync(siteRoot).isSymbolicLink(), false, 'The site root must not be a symlink');
assert.equal(lstatSync(siteRoot).isDirectory(), true, 'The site root must be a directory');

function checkedFile(target) {
  const withinSite = relative(siteRoot, target);
  assert.ok(withinSite && withinSite !== '..' && !withinSite.startsWith(`..${sep}`)
    && !isAbsolute(withinSite), `Reference must stay inside site: ${target}`);
  let current = siteRoot;
  const parts = withinSite.split(sep);
  for (const [index, part] of parts.entries()) {
    assert.ok(readdirSync(current).includes(part),
      `Missing exact-case path component '${part}' in ${current}`);
    current = join(current, part);
    let info;
    assert.doesNotThrow(() => { info = lstatSync(current); }, `Missing local reference: ${current}`);
    assert.equal(info.isSymbolicLink(), false, `Do not traverse a symlink: ${current}`);
    assert.equal(index === parts.length - 1 ? info.isFile() : info.isDirectory(), true,
      index === parts.length - 1 ? `Expected a regular public file: ${current}` : `Expected a directory: ${current}`);
  }
  return target;
}

const sourceFiles = new Map(['index.html', 'styles.css', 'fonts/fonts.css', 'app.js', 'scenario.mjs'].map(name => {
  const path = checkedFile(join(siteRoot, name));
  return [name, { path, source: readFileSync(path, 'utf8') }];
}));

function decodeAttribute(value) {
  const named = { amp: '&', quot: '"', apos: "'", lt: '<', gt: '>' };
  return value.replace(/&(#x[\da-f]+|#\d+|amp|quot|apos|lt|gt);/gi, (entity, name) => {
    if (name[0] !== '#') return named[name.toLowerCase()];
    return String.fromCodePoint(name[1].toLowerCase() === 'x'
      ? parseInt(name.slice(2), 16) : parseInt(name.slice(1), 10));
  });
}

function markupAttributes(source) {
  const result = [];
  const withoutComments = source.replace(/<!--[\s\S]*?-->/g, '');
  for (const [tag] of withoutComments.matchAll(/<[a-z][\w:-]*\b(?:"[^"]*"|'[^']*'|[^'">])*>/gi)) {
    const attributes = tag.replace(/^<[\w:-]+/, '').replace(/\/?>$/, '');
    for (const match of attributes.matchAll(/([^\s"'<>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g)) {
      result.push({ name: match[1].toLowerCase(), value: decodeAttribute(match[2] ?? match[3] ?? match[4] ?? '') });
    }
  }
  return result;
}

function idsOf(source, label) {
  const ids = new Set();
  for (const { value } of markupAttributes(source).filter(attribute => attribute.name === 'id')) {
    assert.ok(value, `Empty id in ${label}`);
    assert.equal(ids.has(value), false, `Duplicate id '${value}' in ${label}`);
    ids.add(value);
  }
  return ids;
}

function checkReference(raw, sourceFile, { fragmentDocument = sourceFile } = {}) {
  const reference = raw.trim();
  assert.ok(reference, `Empty reference in ${sourceFile}`);
  if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(reference)) return false;

  // A fragment-only CSS URL refers to the owning document, not styles.css.
  const base = reference.startsWith('#') ? fragmentDocument : sourceFile;
  const url = new URL(reference, pathToFileURL(base));
  assert.equal(url.protocol, 'file:', `Unexpected local URL scheme: ${reference}`);
  const target = checkedFile(fileURLToPath(url));
  if (url.hash.length > 1) {
    const fragment = decodeURIComponent(url.hash.slice(1));
    assert.ok(['.html', '.svg'].includes(extname(target).toLowerCase()),
      `Fragment checks support the site's HTML/SVG documents, not ${reference}`);
    const ids = idsOf(readFileSync(target, 'utf8'), relative(siteRoot, target));
    assert.equal(ids.has(fragment), true, `Missing fragment '${fragment}' in ${target}`);
  }
  return true;
}

test('index.html has no duplicate IDs', () => {
  const ids = idsOf(sourceFiles.get('index.html').source, 'index.html');
  assert.ok(ids.size > 0, 'Expected section and interaction targets');
});

test('index.html local href/src files and fragment targets resolve inside site', () => {
  const { path, source } = sourceFiles.get('index.html');
  const references = markupAttributes(source).filter(attribute => ['href', 'src'].includes(attribute.name));
  let localCount = 0;
  for (const { value } of references) if (checkReference(value, path)) localCount += 1;
  assert.ok(localCount > 0, 'Expected local page links and assets');
});

test('local reference checks reject a wrong-case filename on any filesystem', () => {
  const index = sourceFiles.get('index.html').path;
  assert.doesNotThrow(() => checkReference('./loopjacking-paper.pdf', index));
  assert.throws(() => checkReference('./LOOPJACKING-PAPER.PDF', index),
    /Missing exact-case path component 'LOOPJACKING-PAPER\.PDF'/);
});

test('the known JavaScript modules resolve their literal local imports to regular files', () => {
  let localCount = 0;
  for (const name of ['app.js', 'scenario.mjs']) {
    const { path, source } = sourceFiles.get(name);
    const references = [
      ...source.matchAll(/^\s*(?:import|export)\s+(?:[\w*\s{},]+\s+from\s+)?(['"])([^'"\r\n]+)\1/gm),
      ...source.matchAll(/\bimport\(\s*(['"])([^'"\r\n]+)\1\s*\)/g)
    ];
    for (const match of references) if (checkReference(match[2], path)) localCount += 1;
  }
  assert.ok(localCount > 0, 'Expected the simulator module import');
});

test('both stylesheets resolve their local url() references without fetching external data', () => {
  for (const name of ['styles.css', 'fonts/fonts.css']) {
    const { path, source } = sourceFiles.get(name);
    const references = [...source.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/url\(\s*(?:"([^"]*)"|'([^']*)'|([^)]*?))\s*\)/gi)];
    assert.ok(references.length > 0, `Expected image or font assets in ${name}`);
    for (const match of references) {
      checkReference(match[1] ?? match[2] ?? match[3], path, { fragmentDocument: sourceFiles.get('index.html').path });
    }
  }
});
