import { paymentFrame } from './scenario.mjs';

document.documentElement.classList.add('js');
const bar = document.querySelector('#scroll-bar');
const links = [...document.querySelectorAll('[data-section]')];
const sections = links.map((link) => document.querySelector(link.getAttribute('href')));
const sidebar = document.querySelector('.sidebar');
const menuToggle = document.querySelector('.toc-toggle');
const currentSection = document.querySelector('[data-current-section]');
menuToggle.hidden = false;
new ResizeObserver(() => {
  const height = getComputedStyle(menuToggle).display === 'none' ? 0 : menuToggle.offsetHeight;
  document.documentElement.style.setProperty('--nav-offset', `${height}px`);
}).observe(menuToggle);

function closeMenu() {
  sidebar.classList.remove('is-open');
  menuToggle.setAttribute('aria-expanded', 'false');
}
menuToggle.addEventListener('click', () => {
  const open = sidebar.classList.toggle('is-open');
  menuToggle.setAttribute('aria-expanded', String(open));
});
sidebar.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && sidebar.classList.contains('is-open')) {
    closeMenu();
    menuToggle.focus();
  }
});
sidebar.addEventListener('focusout', (event) => {
  if (!sidebar.contains(event.relatedTarget)) closeMenu();
});
links.forEach((link) => link.addEventListener('click', () => {
  closeMenu();
  const destination = document.querySelector(link.getAttribute('href'));
  destination.tabIndex = -1;
  destination.focus({ preventScroll: true });
}));

function updateScroll() {
  const root = document.documentElement;
  const range = root.scrollHeight - root.clientHeight;
  bar.style.width = `${range > 0 ? (root.scrollTop / range) * 100 : 0}%`;

  let active = 0;
  sections.forEach((section, index) => {
    if (section && section.getBoundingClientRect().top <= 150) active = index;
  });
  links.forEach((link, index) => {
    link.classList.toggle('active', index === active);
    if (index === active) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  });
  currentSection.textContent = links[active].textContent.trim();
}

document.addEventListener('scroll', updateScroll, { passive: true });
window.addEventListener('resize', updateScroll);
updateScroll();

const pathPanels = [...document.querySelectorAll('[data-path-panel]')];
const pathButtons = [...document.querySelectorAll('[data-path]')];
function selectPath(path) {
  pathButtons.forEach((button) => {
    const selected = button.dataset.path === path;
    button.classList.toggle('selected', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  pathPanels.forEach((panel) => { panel.hidden = panel.dataset.pathPanel !== path; });
}
pathButtons.forEach((button) => button.addEventListener('click', () => selectPath(button.dataset.path)));
selectPath('representation');
document.querySelector('.path-switch').hidden = false;

const glossary = [...document.querySelectorAll('.gloss details')];
glossary.forEach((entry, index) => { entry.open = index === 0; });
let beforePrintState = null;
window.addEventListener('beforeprint', () => {
  if (beforePrintState === null) beforePrintState = glossary.map((entry) => entry.open);
  glossary.forEach((entry) => { entry.open = true; });
});
window.addEventListener('afterprint', () => {
  if (!beforePrintState) return;
  glossary.forEach((entry, index) => { entry.open = beforePrintState[index]; });
  beforePrintState = null;
});

const copyDefinition = document.querySelector('[data-copy-definition]');
const copyStatus = document.querySelector('[data-copy-status]');
copyDefinition.hidden = false;
copyDefinition.addEventListener('click', async () => {
  const definition = ['#definition', '#definition-boundary']
    .map((selector) => document.querySelector(selector).textContent.trim())
    .join('\n\n');
  try {
    if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
    await navigator.clipboard.writeText(definition);
    copyStatus.textContent = 'Definition copied.';
  } catch {
    // Leave the complete definition in place; no permission prompt or hidden fallback.
    copyStatus.textContent = 'Copy is unavailable here. Select the definition and authority boundary above to copy them.';
  }
});

const simulator = document.querySelector('[data-simulator]');
let simIndex = 0;
let autoTimer = null;
const simPrev = simulator.querySelector('[data-sim-prev]');
const simNext = simulator.querySelector('[data-sim-next]');
const simAuto = simulator.querySelector('[data-sim-auto]');
const simReset = simulator.querySelector('[data-sim-reset]');
const simProgress = [...simulator.querySelectorAll('[data-sim-step]')];
const decision = simulator.querySelector('[data-decision]');
const simCounter = simulator.querySelector('[data-sim-index]');
const simTitle = simulator.querySelector('[data-sim-title]');
const simCopy = simulator.querySelector('[data-sim-copy]');
const simVerdict = simulator.querySelector('[data-sim-verdict]');
const experiment = simulator.querySelector('[data-sim-experiment]');
const binding = simulator.querySelector('[data-binding]');
const unchanged = simulator.querySelector('[data-unchanged]');
const announcement = simulator.querySelector('[data-sim-announcement]');

function stopAuto() {
  if (autoTimer) window.clearInterval(autoTimer);
  autoTimer = null;
  simAuto.textContent = '▶ Play';
  simAuto.setAttribute('aria-pressed', 'false');
}

function renderSimulator(index, announce = true) {
  const frame = paymentFrame(index, { binding: binding.checked, unchanged: unchanged.checked });
  simIndex = frame.step;
  simulator.dataset.outcome = frame.outcome;
  simProgress.forEach((button, position) => {
    button.classList.toggle('on', position === simIndex);
    button.classList.toggle('done', position < simIndex);
    if (position === simIndex) button.setAttribute('aria-current', 'step');
    else button.removeAttribute('aria-current');
  });
  for (const kind of ['approved', 'current']) {
    for (const field of ['action', 'amount', 'recipient']) {
      simulator.querySelector(`[data-${kind}-${field}]`).textContent = frame[kind]?.[field] || '—';
    }
  }
  simulator.querySelector('[data-approved-state]').textContent = frame.approved ? 'A · $20' : 'NOT YET';
  simulator.querySelector('[data-current-state]').textContent = frame.changed ? 'B · CHANGED' : frame.current ? 'A · ORIGINAL' : 'NOT YET';
  simulator.querySelector('[data-current-card]').classList.toggle('changed', frame.changed);
  decision.textContent = frame.decision;
  simCounter.textContent = `STEP ${String(simIndex).padStart(2, '0')} / 04`;
  const mode = simulator.querySelector('[data-sim-mode]');
  mode.hidden = !binding.checked && !unchanged.checked;
  mode.textContent = `Comparison: exact check ${binding.checked ? 'on' : 'off'} · request ${unchanged.checked ? 'unchanged' : 'changed'}`;
  simTitle.textContent = frame.title;
  simCopy.textContent = frame.copy;
  simVerdict.textContent = frame.verdict;
  simVerdict.className = `sim-verdict ${frame.tone}`;
  const experimentResult = simulator.querySelector('[data-experiment-result]');
  experimentResult.textContent = frame.verdict;
  experimentResult.className = `sim-verdict ${frame.tone}`;
  experiment.hidden = simIndex !== 4;
  simPrev.disabled = simIndex === 0;
  simNext.textContent = simIndex === 0 ? 'Start →' : simIndex === 4 ? 'Replay →' : 'Next →';
  if (announce) announcement.textContent = `Step ${simIndex} of 4. ${frame.title} ${frame.verdict}`;
  if (simIndex === 4) stopAuto();
}

simPrev.addEventListener('click', () => { stopAuto(); renderSimulator(simIndex - 1); });
simNext.addEventListener('click', () => {
  stopAuto();
  const starting = simIndex === 0;
  renderSimulator(simIndex === 4 ? 0 : simIndex + 1);
  if (starting) simulator.querySelector('.sim-controls').scrollIntoView({ block: 'start', behavior: 'instant' });
});
simReset.addEventListener('click', () => { stopAuto(); binding.checked = false; unchanged.checked = false; renderSimulator(0); });
simProgress.forEach((button) => button.addEventListener('click', () => { stopAuto(); renderSimulator(Number(button.dataset.simStep)); }));
simAuto.addEventListener('click', () => {
  if (autoTimer) return stopAuto();
  if (simIndex === 4) renderSimulator(0);
  simAuto.textContent = 'Ⅱ Pause';
  simAuto.setAttribute('aria-pressed', 'true');
  autoTimer = window.setInterval(() => {
    renderSimulator(simIndex + 1);
  }, 10000);
});
for (const input of [binding, unchanged]) input.addEventListener('change', () => {
  stopAuto();
  renderSimulator(simIndex);
});
document.addEventListener('visibilitychange', () => { if (document.hidden) stopAuto(); });
new IntersectionObserver(([entry]) => { if (!entry.isIntersecting) stopAuto(); }).observe(simulator);
renderSimulator(0, false);
simulator.hidden = false;
document.querySelector("#s5").classList.add("simulator-ready");

const questions = [
  {
    prompt: 'The product skips the human and sends $20,000. Is that Loopjacking?',
    options: ['Yes — any dangerous payment qualifies.', 'No — there was no genuine approval to hijack.', 'Only if the workflow uses A2A.'],
    answer: 1,
    explanation: 'Loopjacking needs a real human decision for A. Skipping or forging approval is a different failure.'
  },
  {
    prompt: 'How can approval for the $20 refund authorize the $20,000 transfer?',
    options: ['Only if the request changes after the human clicks approve.', 'The complete request already differs from the approval view, or an attacker changes it after approval.', 'Only when a language model rewrites text.'],
    answer: 1,
    explanation: 'B may already be hidden in the request, or attacker-reachable state may change A into B after approval.'
  },
  {
    prompt: 'A paused workflow accepts a new message. Is that alone proof of Loopjacking?',
    options: ['Yes — mutation is enough.', 'Only if the task uses payments.', 'No — the old approval must actually authorize a materially different effect.'],
    answer: 2,
    explanation: 'Continuation is a carrier, not the security result. The attack also needs genuine approval, material mismatch, attacker influence, and product-owned consumption.'
  },
  {
    prompt: 'What should the product do before releasing the payment?',
    options: ['Check only that the workflow has an approval.', 'Rebuild the current payment and compare it with the complete operation the human approved.', 'Trust the latest instruction because it belongs to the same workflow.'],
    answer: 1,
    explanation: 'If the current effect differs materially, the product must reject it or request a new approval.'
  },
  {
    prompt: 'A person approves sharing a document with a teammate. An attacker who cannot share it directly changes the recipient, and the app uses the same approval to share it outside the team. What happened?',
    options: ['The approval covers any recipient because the document stayed the same.', 'Loopjacking: the app used a real approval for a recipient the person never approved.', 'Nothing changed that matters to authorization.'],
    answer: 1,
    explanation: 'The recipient is part of the approved action. In this fictional example, the attacker crosses a permission boundary by making the app consume the old approval for a different recipient. The same principle applies beyond payments.'
  }
];

const quiz = document.querySelector('[data-quiz]');
const quizDone = document.querySelector('[data-quiz-done]');
const reviewedQuestions = new Set();
quizDone.textContent = '';

function updateQuizProgress() {
  const reviewed = reviewedQuestions.size;
  quizDone.textContent = reviewed === questions.length
    ? `All ${questions.length} explanations reviewed. You can retry any question to practice.`
    : `${reviewed} of ${questions.length} explanations reviewed.`;
  quizDone.classList.toggle('show', reviewed > 0);
}

questions.forEach((question, index) => {
  const article = document.createElement('article');
  article.className = 'question';
  const label = document.createElement('span');
  label.textContent = `QUESTION ${String(index + 1).padStart(2, '0')}`;
  const heading = document.createElement('h3');
  heading.id = `quiz-question-${index + 1}`;
  heading.textContent = question.prompt;
  const options = document.createElement('div');
  options.className = 'options';
  options.setAttribute('role', 'group');
  options.setAttribute('aria-labelledby', heading.id);
  const feedback = document.createElement('div');
  feedback.setAttribute('role', 'status');
  feedback.setAttribute('aria-live', 'polite');
  feedback.setAttribute('aria-atomic', 'true');
  const explanation = document.createElement('div');
  explanation.className = 'explanation';
  feedback.append(explanation);
  const retry = document.createElement('button');
  retry.type = 'button';
  retry.className = 'option quiz-retry';
  retry.textContent = 'Try this question again';
  retry.setAttribute('aria-label', `Try question ${index + 1} again`);
  let selectedButton = null;

  retry.addEventListener('click', () => {
    delete article.dataset.answered;
    [...options.children].forEach((candidate) => {
      candidate.removeAttribute('aria-disabled');
      candidate.classList.remove('correct', 'wrong');
    });
    explanation.textContent = `Question ${index + 1} is ready to try again. Choose an answer.`;
    selectedButton.focus();
    retry.remove();
  });

  question.options.forEach((text, optionIndex) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'option';
    const key = document.createElement('b');
    key.textContent = String.fromCharCode(65 + optionIndex);
    const copy = document.createElement('span');
    copy.textContent = text;
    button.append(key, copy);
    button.addEventListener('click', () => {
      if (article.dataset.answered) return;
      article.dataset.answered = 'true';
      selectedButton = button;
      [...options.children].forEach((candidate, candidateIndex) => {
        candidate.setAttribute('aria-disabled', 'true');
        if (candidateIndex === question.answer) candidate.classList.add('correct');
      });
      const correct = optionIndex === question.answer;
      if (!correct) button.classList.add('wrong');
      explanation.classList.add('show');
      explanation.textContent = correct
        ? `Correct. ${question.explanation}`
        : `Not quite. The correct answer is ${String.fromCharCode(65 + question.answer)}. ${question.explanation}`;
      article.append(retry);
      reviewedQuestions.add(index);
      updateQuizProgress();
    });
    options.append(button);
  });

  article.append(label, heading, options, feedback);
  quiz.append(article);
});

document.querySelector("#s10").classList.add("quiz-ready");
