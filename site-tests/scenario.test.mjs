import { test } from 'node:test';
import assert from 'node:assert/strict';
import { paymentFrame } from '../site/scenario.mjs';

test('no approval is implied before the human decision', () => {
  for (const step of [0, 1]) {
    assert.equal(paymentFrame(step).approved, null);
    assert.equal(paymentFrame(step).outcome, 'pending');
  }
  assert.equal(paymentFrame(0).current, null);
  assert.equal(paymentFrame(1).current.amount, '$20');
});

test('the approved record stays exact while three current fields change', () => {
  const original = paymentFrame(2);
  const changed = paymentFrame(3);
  assert.deepEqual(original.approved, original.current);
  assert.deepEqual(changed.approved, original.approved);
  for (const field of ['action', 'amount', 'recipient']) {
    assert.notEqual(changed.current[field], changed.approved[field]);
  }
  assert.equal(changed.outcome, 'pending');
});

for (const [binding, unchanged, outcome] of [
  [false, false, 'loopjacked'],
  [true, false, 'blocked'],
  [false, true, 'authorized'],
  [true, true, 'authorized']
]) {
  test(`use-time outcome: check=${binding}, unchanged=${unchanged}`, () => {
    const result = paymentFrame(4, { binding, unchanged });
    assert.equal(result.outcome, outcome);
    assert.equal(result.approved.amount, '$20');
    assert.equal(result.current.amount, unchanged ? '$20' : '$20,000');
    if (outcome === 'blocked') assert.match(result.verdict, /no matching approval/);
  });
}

test('approval descriptors cannot be changed by an earlier rendering', () => {
  const frame = paymentFrame(2);
  assert.throws(() => { frame.approved.amount = '$99'; }, TypeError);
  assert.equal(paymentFrame(4).approved.amount, '$20');
});

test('step input is bounded and rendering is repeatable', () => {
  for (const input of [undefined, NaN, -1, 'not a step']) assert.equal(paymentFrame(input).step, 0);
  assert.equal(paymentFrame(99).step, 4);
  assert.deepEqual(paymentFrame(3), paymentFrame(3));
});
