// A fictional, browser-only teaching model. No payments or product APIs.
// Once granted, the approval is assumed valid, unused, and in the correct scope.
// The model compares actions; it does not implement approval lifecycle checks.
const refund = Object.freeze({ action: 'Refund', amount: '$20', recipient: 'Customer' });
const transfer = Object.freeze({ action: 'Transfer', amount: '$20,000', recipient: 'Attacker' });

export function paymentFrame(index, { binding = false, unchanged = false } = {}) {
  const step = Math.max(0, Math.min(4, Math.trunc(Number(index)) || 0));
  const changed = step >= 3 && !unchanged;
  const approved = step >= 2 ? refund : null;
  const current = step >= 1 ? (changed ? transfer : refund) : null;
  const frame = {
    step, approved, current, changed,
    decision: approved ? 'Yes to the $20 refund. No new approval.' : 'No approval yet.',
    tone: approved ? 'ok' : '',
    outcome: 'pending',
    title: ['Follow one approval.', 'A $20 refund is proposed.', 'The human approves the refund.', 'The request changes. The approval does not.', ''][step],
    copy: [
      'Start with a small refund. Watch what happens to its approval. This is a fictional example, not a live payment.',
      'Here, the requester is the attacker. They can propose and update a payment, but cannot approve or directly execute it. The human is shown the action, amount, and recipient.',
      'The human sees and approves this exact refund. Keep the left-hand record in view: it will not change.',
      'An attacker-reachable update replaces the pending refund with a transfer. The original approval remains recorded.',
      ''
    ][step],
    verdict: [
      'No action is authorized yet.',
      'A proposal is not permission to execute.',
      'Approved and current match: refund $20 to the customer.',
      'Mismatch: action, amount, and recipient all changed.',
      ''
    ][step]
  };
  if (step === 3 && unchanged) {
    frame.title = 'The original request stays unchanged.';
    frame.copy = 'No substitution happens in this comparison. The current request is still the exact refund the human approved.';
    frame.verdict = 'Approved and current still match.';
  } else if (changed) frame.tone = 'bad';

  if (step === 4) {
    if (!changed) {
      frame.outcome = 'authorized';
      frame.tone = 'ok';
      frame.title = 'The approved $20 refund can proceed.';
      frame.copy = binding
        ? 'The use-time check compares the complete current action with the approval record. They match, and the approval is still valid. The unchanged refund can proceed.'
        : 'The current request still matches the approved refund, and the approval is still valid. This does not prove the workflow would reject a changed request.';
      frame.verdict = 'AUTHORIZED · $20 refund to the customer.';
    } else if (binding) {
      frame.outcome = 'blocked';
      frame.tone = 'ok';
      frame.title = 'The $20,000 transfer is blocked.';
      frame.copy = 'The use-time check finds three changed fields. The old approval cannot authorize this transfer. The product must reject it or seek a new approval.';
      frame.verdict = 'BLOCKED · The transfer has no matching approval.';
    } else {
      frame.outcome = 'loopjacked';
      frame.title = 'The product lets the transfer proceed.';
      frame.copy = 'Product logic checks that an approval exists, but not what it covers. It uses the genuine refund approval to release a different action.';
      frame.verdict = 'LOOPJACKED · A $20 approval releases $20,000.';
      frame.decision = 'The $20 refund approval is wrongly consumed for the transfer.';
    }
  }
  return frame;
}
