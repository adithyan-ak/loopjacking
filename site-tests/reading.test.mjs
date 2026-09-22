import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { runInNewContext } from 'node:vm';
import { paymentFrame } from '../site/scenario.mjs';

const html = readFileSync(new URL('../site/index.html', import.meta.url), 'utf8');
const app = readFileSync(new URL('../site/app.js', import.meta.url), 'utf8');
const figure = readFileSync(new URL('../site/loopjacking-explained.svg', import.meta.url), 'utf8');

// Front-page metadata was checked visually and with pdfinfo on 2026-09-18.
// This pin requires a fresh citation review if the downloadable paper is replaced;
// it does not parse the PDF or establish its scientific correctness.
const reviewedPaperSha256 = '5cb2724dffa8e577518716025d04466b9e39f5a75a6285b69a2f8e0467aab7f7';

// These checks inspect this page's source, not a browser DOM or computed styles.
// They do not certify printed layout, accessibility, font loading, or no-JS rendering.
// The small reader only tracks markup ancestry and text needed by these assertions.
function readMarkup(source) {
  const root = { tag: '#root', attrs: new Map(), children: [], parent: null };
  const stack = [root];
  const elements = [];
  const voidTags = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']);
  const tokens = source.matchAll(/<!--[\s\S]*?-->|<![^>]*>|<\/?[\w:-]+\b(?:"[^"]*"|'[^']*'|[^'">])*>|[^<]+/g);

  for (const [token] of tokens) {
    if (token.startsWith('<!')) continue;
    if (token.startsWith('</')) {
      const tag = token.match(/^<\/([\w:-]+)/)[1].toLowerCase();
      assert.equal(stack.at(-1).tag, tag, `Unexpected closing tag ${tag} in source reader`);
      stack.pop();
      continue;
    }
    if (!token.startsWith('<')) {
      stack.at(-1).children.push(token);
      continue;
    }

    const [, rawTag, rawAttrs] = token.match(/^<([\w:-]+)([\s\S]*?)\/?\s*>$/);
    const attrs = new Map();
    for (const match of rawAttrs.matchAll(/([^\s"'<>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g)) {
      attrs.set(match[1].toLowerCase(), match[2] ?? match[3] ?? match[4] ?? '');
    }
    const element = { tag: rawTag.toLowerCase(), attrs, children: [], parent: stack.at(-1) };
    element.parent.children.push(element);
    elements.push(element);
    if (!voidTags.has(element.tag) && !token.endsWith('/>')) stack.push(element);
  }
  assert.equal(stack.length, 1, 'Source reader found unclosed markup');
  return elements;
}

function textOf(element) {
  return element.children.map(child => typeof child === 'string' ? child : textOf(child)).join(' ').replace(/\s+/g, ' ').trim();
}

function hasClass(element, name) {
  return (element.attrs.get('class') || '').split(/\s+/).includes(name);
}

function hasAncestor(element, predicate) {
  for (let current = element; current; current = current.parent) {
    if (predicate(current)) return true;
  }
  return false;
}

function hiddenInMarkup(element) {
  return hasAncestor(element, current => current.attrs.has('hidden'));
}

const pageElements = readMarkup(html);
const figureElements = readMarkup(figure);

test('the opening identifies the research context and retains the fictional-example boundary', () => {
  const hero = pageElements.find(element => element.attrs.get('id') === 's0');
  assert.ok(hero);
  const badge = pageElements.find(element => hasClass(element, 'pill')
    && hasAncestor(element, ancestor => ancestor === hero));
  assert.ok(badge);
  assert.equal(hiddenInMarkup(badge), false);
  assert.equal(textOf(badge), 'AI AGENT SECURITY');
  const description = pageElements.find(element => element.tag === 'meta'
    && element.attrs.get('name') === 'description')?.attrs.get('content');
  assert.match(description, /AI-agent workflows/);
  assert.match(description, /fictional \$20-to-\$20,000 example/);
  assert.match(textOf(hero), /not a claim of actual losses/i);
  assert.match(textOf(hero), /attacker cannot authorize the transfer/i);
});

test('the visible research citation accompanies the reviewed paper', () => {
  const citation = pageElements.find(element => element.attrs.get('id') === 'paper-citation');
  assert.ok(citation);
  assert.equal(hiddenInMarkup(citation), false);
  const title = citation.children.find(element => typeof element !== 'string' && element.tag === 'cite');
  assert.ok(title, 'The citation must identify the paper title');
  assert.equal(textOf(title), 'Loopjacking: Hijacking Human-in-the-Loop Approval');
  assert.match(textOf(citation), /Adithyan Arun Kumar/);
  const date = pageElements.find(element => element.tag === 'time'
    && hasAncestor(element, ancestor => ancestor === citation));
  assert.ok(date, 'The citation must include the month shown on the paper');
  assert.equal(date?.attrs.get('datetime'), '2026-09');
  assert.equal(textOf(date), 'September 2026');
  const link = pageElements.find(element => hasClass(element, 'read-paper'));
  assert.equal(link?.attrs.get('href'), './loopjacking-paper.pdf');
  assert.equal(link?.attrs.get('aria-describedby'), citation.attrs.get('id'));
  const pdf = readFileSync(new URL('../site/loopjacking-paper.pdf', import.meta.url));
  assert.equal(createHash('sha256').update(pdf).digest('hex'), reviewedPaperSha256,
    'Paper changed: inspect its title page and review the displayed citation before updating this pin');
});

test('both mechanism explanations exist in ordinary, initially unhidden HTML', () => {
  const panels = pageElements.filter(element => element.attrs.has('data-path-panel'));
  assert.equal(panels.length, 2);
  const representation = panels.find(element => element.attrs.get('data-path-panel') === 'representation');
  const substitution = panels.find(element => element.attrs.get('data-path-panel') === 'substitution');
  assert.ok(representation);
  assert.ok(substitution);
  for (const panel of panels) {
    assert.equal(hiddenInMarkup(panel), false);
    assert.equal(hasAncestor(panel, element => ['script', 'template', 'noscript'].includes(element.tag)), false);
  }
  assert.match(textOf(representation), /before approval/i);
  assert.match(textOf(representation), /approval view left out/i);
  assert.match(textOf(substitution), /after.*(?:click|approval)/i);
  assert.match(textOf(substitution), /approval for the refund/i);
});

test('JavaScript-only buttons begin hidden themselves or through an ancestor', () => {
  const buttons = pageElements.filter(element => element.tag === 'button');
  assert.ok(buttons.length > 0, 'Expected enhancement controls in the source');
  for (const button of buttons) {
    assert.equal(hiddenInMarkup(button), true, `Initially exposed inert button: ${textOf(button)}`);
  }
});

test('the simulator declares one live region for its outcome announcements', () => {
  const liveRegions = pageElements.filter(element => {
    const inSimulator = hasAncestor(element, ancestor => ancestor.attrs.has('data-simulator'));
    const live = element.attrs.get('aria-live');
    const role = element.attrs.get('role');
    return inSimulator && (['polite', 'assertive'].includes(live)
      || (live !== 'off' && ['status', 'alert', 'log'].includes(role)));
  });
  assert.equal(liveRegions.length, 1, 'Do not announce the same simulator result through two regions');
  assert.equal(liveRegions[0].attrs.has('data-sim-announcement'), true);
  assert.equal(liveRegions[0].attrs.get('aria-live'), 'polite');
  assert.equal(liveRegions[0].attrs.get('aria-atomic'), 'true');
});

test('all four glossary explanations start open for static reading', () => {
  const entries = pageElements.filter(element => element.tag === 'details'
    && hasAncestor(element, ancestor => hasClass(ancestor, 'gloss')));
  assert.equal(entries.length, 4);
  for (const entry of entries) assert.equal(entry.attrs.has('open'), true);
});

test('the introductory binding explanation covers a mismatch before or after approval', () => {
  const entry = pageElements.find(element => element.tag === 'details'
    && hasAncestor(element, ancestor => hasClass(ancestor, 'gloss'))
    && textOf(element).startsWith('binding '));
  assert.ok(entry);
  const copy = textOf(entry);
  assert.match(copy, /complete action.*human reviewed and approved/i);
  assert.match(copy, /material mismatch/i);
  assert.match(copy, /hidden before approval/i);
  assert.match(copy, /introduced afterward/i);
});

test('interactive and static walkthroughs introduce the same requester and authority boundary', () => {
  const fallback = pageElements.find(element => hasClass(element, 'reading-fallback'));
  const firstStep = pageElements.find(element => element.tag === 'li'
    && hasAncestor(element, ancestor => ancestor === fallback));
  assert.ok(firstStep);
  for (const copy of [paymentFrame(1).copy, textOf(firstStep)]) {
    assert.match(copy, /requester is the attacker/i);
    assert.match(copy, /can propose and update a payment/i);
    assert.match(copy, /cannot approve or directly execute it/i);
  }
});

test('ordinary HTML contains the complete walkthrough and quiz reading fallbacks', () => {
  for (const className of ['reading-fallback', 'quiz-fallback']) {
    const fallback = pageElements.find(element => hasClass(element, className));
    assert.ok(fallback, `Missing ${className}`);
    assert.equal(hiddenInMarkup(fallback), false);
    assert.equal(hasAncestor(fallback, element => ['script', 'template', 'noscript'].includes(element.tag)), false);
  }
  const walkthrough = pageElements.find(element => hasClass(element, 'reading-fallback'));
  assert.match(textOf(walkthrough), /\$20 refund/);
  assert.match(textOf(walkthrough), /\$20,000 transfer/);
  assert.match(textOf(walkthrough), /original approval remains/i);
  assert.match(textOf(walkthrough), /(?:reject|block).*changed transfer/i);
  assert.match(textOf(walkthrough), /unchanged \$20 refund can still proceed/i);
});

test('the walkthrough and defense qualify release with a still-valid approval', () => {
  const note = pageElements.find(element => hasClass(element, 'simulator-note'));
  assert.ok(note);
  assert.equal(hiddenInMarkup(note), false);
  assert.equal(hasAncestor(note, element => ['script', 'template', 'noscript'].includes(element.tag)), false);
  assert.match(textOf(note), /assumes a still-valid, unused approval in the correct workflow/i);
  for (const binding of [false, true]) {
    assert.match(paymentFrame(4, { binding, unchanged: true }).copy, /approval is still valid/i);
  }
  const fallback = pageElements.find(element => hasClass(element, 'reading-fallback'));
  const defense = pageElements.find(element => element.attrs.get('id') === 's9');
  for (const section of [fallback, defense]) {
    assert.ok(section);
    assert.match(textOf(section), /with a matching, still-valid approval/i);
  }
});

test('the evidence distinguishes study controls from released fixes for every case', () => {
  const row = pageElements.find(element => element.tag === 'article'
    && hasAncestor(element, ancestor => hasClass(ancestor, 'evidence-list'))
    && textOf(element).includes('Safe paths'));
  assert.ok(row);
  const copy = textOf(row);
  assert.match(copy, /released fix/);
  assert.match(copy, /supported safe configuration/);
  assert.match(copy, /researcher-added check/);
  assert.match(copy, /not released fixes for every case/);
  assert.match(copy, /TESTED CONTROLS/);
});

test('the downloadable figure keeps its fictional and authority boundaries in visible text and description', () => {
  for (const format of ['svg', 'png']) {
    const link = pageElements.find(element => element.tag === 'a'
      && element.attrs.get('href') === `./loopjacking-explained.${format}`);
    assert.ok(link?.attrs.has('download'), `The inspected figure must be offered as ${format}`);
  }

  const visibleText = figureElements.filter(element => element.tag === 'text').map(textOf).join(' ');
  const description = figureElements.find(element => element.tag === 'desc');
  assert.ok(description);
  for (const copy of [visibleText, textOf(description)]) {
    assert.match(copy, /cannot approve or send this transfer directly/i);
    assert.match(copy, /(?:fictional|illustrative)/i);
    assert.match(copy, /(?:not|do not).*actual losses/i);
    assert.match(copy, /\$20\b/);
    assert.match(copy, /\$20,000\b/);
  }
});

function glossaryPrintHarness() {
  const start = app.indexOf('const glossary =');
  const end = app.indexOf('const copyDefinition =', start);
  assert.ok(start >= 0 && end > start, 'Locate the actual glossary setup and print handlers in app.js');
  const entries = Array.from({ length: 4 }, () => ({ open: true }));
  const handlers = new Map();
  runInNewContext(app.slice(start, end), {
    document: {
      querySelectorAll(selector) {
        assert.equal(selector, '.gloss details');
        return entries;
      }
    },
    window: {
      addEventListener(event, handler) {
        if (!handlers.has(event)) handlers.set(event, []);
        handlers.get(event).push(handler);
      }
    }
  }, { timeout: 1000 });
  assert.ok(handlers.has('beforeprint'));
  assert.ok(handlers.has('afterprint'));
  return {
    state: () => entries.map(entry => entry.open),
    setState: state => entries.forEach((entry, index) => { entry.open = state[index]; }),
    emit: event => (handlers.get(event) || []).forEach(handler => handler())
  };
}

test('print handlers expand the glossary then restore the reader’s choices', () => {
  const glossary = glossaryPrintHarness();
  const original = [false, true, false, true];
  glossary.setState(original);
  glossary.emit('beforeprint');
  assert.deepEqual(glossary.state(), [true, true, true, true]);
  glossary.emit('afterprint');
  assert.deepEqual(glossary.state(), original);
});

test('repeated beforeprint events preserve the first snapshot', () => {
  const glossary = glossaryPrintHarness();
  const original = [true, false, true, false];
  glossary.setState(original);
  glossary.emit('beforeprint');
  glossary.emit('beforeprint');
  glossary.emit('afterprint');
  assert.deepEqual(glossary.state(), original);
});

test('consecutive print sessions take fresh snapshots and unmatched afterprint is harmless', () => {
  const glossary = glossaryPrintHarness();
  for (const original of [[false, false, false, false], [false, true, true, false]]) {
    glossary.setState(original);
    glossary.emit('afterprint');
    assert.deepEqual(glossary.state(), original);
    glossary.emit('beforeprint');
    glossary.emit('afterprint');
    glossary.emit('afterprint');
    assert.deepEqual(glossary.state(), original);
  }
});

function copyDefinitionHarness(clipboard) {
  const start = app.indexOf('const copyDefinition =');
  const end = app.indexOf('const simulator =', start);
  assert.ok(start >= 0 && end > start, 'Locate the actual copy-definition listener in app.js');
  const definition = pageElements.find(element => element.attrs.get('id') === 'definition');
  const boundary = pageElements.find(element => element.attrs.get('id') === 'definition-boundary');
  const statusSource = pageElements.find(element => element.attrs.has('data-copy-status'));
  assert.ok(definition, 'The copied definition must exist in the page');
  assert.ok(boundary, 'The copied authority boundary must exist in the page');
  assert.ok(statusSource);
  assert.equal(hiddenInMarkup(statusSource), false, 'Fallback status must not be hidden in markup');
  assert.equal(statusSource.attrs.get('aria-live'), 'polite');

  let click;
  const button = {
    hidden: true,
    addEventListener(event, listener) {
      assert.equal(event, 'click');
      click = listener;
    }
  };
  const status = { textContent: '' };
  const definitionNode = { textContent: textOf(definition) };
  const boundaryNode = { textContent: textOf(boundary) };
  const nodes = new Map([
    ['[data-copy-definition]', button],
    ['[data-copy-status]', status],
    ['#definition', definitionNode],
    ['#definition-boundary', boundaryNode]
  ]);
  runInNewContext(app.slice(start, end), {
    navigator: clipboard === undefined ? {} : { clipboard },
    document: {
      querySelector(selector) {
        assert.ok(nodes.has(selector), `Unexpected selector in copy listener: ${selector}`);
        return nodes.get(selector);
      }
    }
  }, { timeout: 1000 });
  assert.equal(typeof click, 'function');
  assert.equal(button.hidden, false);
  return { click, status, definitionNode, boundaryNode };
}

test('copy-definition listener copies both actual page paragraphs after a click', async () => {
  const writes = [];
  const copy = copyDefinitionHarness({ writeText: async text => { writes.push(text); } });
  assert.deepEqual(writes, [], 'Initialization must not write to the clipboard');
  await assert.doesNotReject(() => copy.click());
  assert.deepEqual(writes, [`${copy.definitionNode.textContent}\n\n${copy.boundaryNode.textContent}`]);
  assert.match(writes[0], /lack equivalent direct authority/i);
  assert.match(copy.status.textContent, /definition copied/i);
});

for (const clipboardState of ['rejected', 'absent']) {
  test(`copy-definition listener handles ${clipboardState} clipboard without a rejected handler promise`, async () => {
    let attempts = 0;
    const clipboard = clipboardState === 'absent' ? undefined : {
      async writeText() {
        attempts += 1;
        throw new Error('Clipboard write rejected by test');
      }
    };
    const copy = copyDefinitionHarness(clipboard);
    const originalDefinition = copy.definitionNode.textContent;
    const originalBoundary = copy.boundaryNode.textContent;
    await assert.doesNotReject(() => copy.click());
    assert.equal(attempts, clipboardState === 'rejected' ? 1 : 0);
    assert.match(copy.status.textContent, /copy is unavailable/i);
    assert.match(copy.status.textContent, /select.*definition.*authority boundary/i);
    assert.equal(copy.definitionNode.textContent, originalDefinition);
    assert.equal(copy.boundaryNode.textContent, originalBoundary);
  });
}
