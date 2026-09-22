import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { paymentFrame } from '../site/scenario.mjs';

const app = readFileSync(new URL('../site/app.js', import.meta.url), 'utf8');

// Execute the actual simulator setup, renderer, and event listeners with fake
// timers and minimal elements. These tests verify callback behavior and requested
// interval duration, not browser visibility delivery, elapsed time, focus, layout,
// or what a screen reader announces.
function element(dataset = {}) {
  const listeners = new Map();
  const attributes = new Map();
  const classes = new Set();
  return {
    dataset, attributes, textContent: '', hidden: false, checked: false, disabled: false,
    classList: {
      add: name => classes.add(name),
      toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); }
    },
    setAttribute: (name, value) => attributes.set(name, value),
    removeAttribute: name => attributes.delete(name),
    addEventListener(event, listener) {
      if (!listeners.has(event)) listeners.set(event, []);
      listeners.get(event).push(listener);
    },
    emit: event => (listeners.get(event) || []).forEach(listener => listener()),
    scrollIntoView() {}
  };
}

function playbackHarness() {
  const start = app.indexOf('const simulator =');
  const end = app.indexOf('const questions =', start);
  assert.ok(start >= 0 && end > start, 'Locate the actual simulator block in app.js');
  const controls = new Map();
  for (const name of [
    'sim-prev', 'sim-next', 'sim-auto', 'sim-reset', 'decision', 'sim-index',
    'sim-title', 'sim-copy', 'sim-verdict', 'sim-experiment', 'binding',
    'unchanged', 'sim-announcement', 'approved-state', 'current-state',
    'current-card', 'sim-mode', 'experiment-result'
  ]) controls.set(`[data-${name}]`, element());
  for (const kind of ['approved', 'current']) {
    for (const field of ['action', 'amount', 'recipient']) {
      controls.set(`[data-${kind}-${field}]`, element());
    }
  }
  controls.set('.sim-controls', element());
  const progress = Array.from({ length: 5 }, (_, index) => element({ simStep: String(index) }));
  const simulator = element();
  const section = element();
  simulator.querySelector = selector => {
    assert.ok(controls.has(selector), `Unexpected simulator selector: ${selector}`);
    return controls.get(selector);
  };
  simulator.querySelectorAll = selector => {
    assert.equal(selector, '[data-sim-step]');
    return progress;
  };

  const documentListeners = new Map();
  const document = {
    hidden: false,
    querySelector(selector) {
      assert.ok(['[data-simulator]', '#s5'].includes(selector));
      return selector === '[data-simulator]' ? simulator : section;
    },
    addEventListener(event, listener) {
      if (!documentListeners.has(event)) documentListeners.set(event, []);
      documentListeners.get(event).push(listener);
    }
  };
  let intersectionCallback;
  let nextTimerId = 1;
  const timers = new Map();
  const scheduledDelays = [];
  const clearedTimers = [];
  runInNewContext(app.slice(start, end), {
    document, paymentFrame,
    window: {
      setInterval(callback, delay) {
        const id = nextTimerId++;
        timers.set(id, callback);
        scheduledDelays.push(delay);
        return id;
      },
      clearInterval(id) {
        clearedTimers.push(id);
        timers.delete(id);
      }
    },
    IntersectionObserver: class {
      constructor(callback) { intersectionCallback = callback; }
      observe(target) { assert.equal(target, simulator); }
    }
  }, { timeout: 1000 });
  assert.equal(typeof intersectionCallback, 'function');
  assert.ok(documentListeners.has('visibilitychange'));
  return {
    auto: controls.get('[data-sim-auto]'),
    counter: controls.get('[data-sim-index]'),
    timers, scheduledDelays, clearedTimers,
    tick() {
      for (const [id, callback] of [...timers]) if (timers.has(id)) callback();
    },
    visibility(hidden) {
      document.hidden = hidden;
      for (const callback of documentListeners.get('visibilitychange')) callback();
    },
    intersection: isIntersecting => intersectionCallback([{ isIntersecting }])
  };
}

test('playback starts only on request and schedules ten-second steps', () => {
  const playback = playbackHarness();
  assert.equal(playback.timers.size, 0);
  assert.match(playback.counter.textContent, /STEP 00/);
  playback.auto.emit('click');
  assert.deepEqual(playback.scheduledDelays, [10000]);
  assert.equal(playback.auto.attributes.get('aria-pressed'), 'true');
  playback.tick();
  assert.match(playback.counter.textContent, /STEP 01/);
  playback.auto.emit('click');
  assert.equal(playback.timers.size, 0);
  assert.equal(playback.auto.attributes.get('aria-pressed'), 'false');
});

for (const trigger of ['page hidden', 'simulator offscreen']) {
  test(`${trigger} cancels playback and returning does not restart it`, () => {
    const playback = playbackHarness();
    playback.auto.emit('click');
    playback.tick();
    const pausedAt = playback.counter.textContent;

    if (trigger === 'page hidden') {
      playback.visibility(false);
      assert.equal(playback.timers.size, 1, 'Visible-page event must not stop playback');
      playback.visibility(true);
    } else {
      playback.intersection(true);
      assert.equal(playback.timers.size, 1, 'An intersecting simulator must keep playing');
      playback.intersection(false);
    }
    assert.deepEqual(playback.clearedTimers, [1]);
    assert.equal(playback.timers.size, 0);
    assert.equal(playback.auto.attributes.get('aria-pressed'), 'false');
    assert.match(playback.auto.textContent, /Play/);

    if (trigger === 'page hidden') playback.visibility(false);
    else playback.intersection(true);
    playback.tick();
    assert.equal(playback.timers.size, 0);
    assert.equal(playback.counter.textContent, pausedAt);
    assert.deepEqual(playback.scheduledDelays, [10000]);

    playback.auto.emit('click');
    assert.equal(playback.timers.size, 1, 'An explicit Play may resume after return');
    playback.tick();
    assert.match(playback.counter.textContent, /STEP 02/);
  });
}

test('playback stops at the final outcome instead of scheduling further steps', () => {
  const playback = playbackHarness();
  playback.auto.emit('click');
  for (let step = 0; step < 4; step += 1) playback.tick();
  assert.match(playback.counter.textContent, /STEP 04/);
  assert.equal(playback.timers.size, 0);
  assert.equal(playback.auto.attributes.get('aria-pressed'), 'false');
  playback.tick();
  assert.match(playback.counter.textContent, /STEP 04/);
});
