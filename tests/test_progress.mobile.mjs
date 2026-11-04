// Node test for mobile/src/progress.js (Stage 8a).
// mobile/package.json has no "type": "module", so we read the ESM source,
// strip the `export ` keywords, and evaluate it in a function scope.

import { readFileSync } from 'node:fs';
import assert from 'node:assert';

const source = readFileSync(
  new URL('../mobile/src/progress.js', import.meta.url),
  'utf8',
);
const stripped = source.replace(/^export /gm, '');
const { computeCurrentStreak, computeAccuracyTotals, computeProgressSummary, computeTopicBreakdown, computeTopicOptions } =
  new Function(`${stripped}; return { computeCurrentStreak, computeAccuracyTotals, computeProgressSummary, computeTopicBreakdown, computeTopicOptions };`)();

const attempts = [];

function entry(id, createdAt, topic, attempt) {
  return {
    id,
    createdAt,
    exam: 'Banking',
    subject: 'Economy',
    topic,
    relevance: '',
    questionCount: attempt ? attempt.total : 3,
    attempt: attempt || null,
    result: {},
  };
}

function attempt(daysAgo, correct, total, atHour = 10) {
  const at = new Date();
  at.setDate(at.getDate() - daysAgo);
  at.setHours(atHour, 30, 0, 0);
  attempts.push(at.toISOString());
  return { correct, answered: total, total, accuracy: Math.round((correct / total) * 100), at: at.toISOString() };
}

// --- computeAccuracyTotals -------------------------------------------------
{
  const history = [
    entry('a', attempts.at(0) || new Date().toISOString(), 'Monetary Policy', attempt(0, 3, 3)),
    entry('b', attempts.at(0) || new Date().toISOString(), 'Monetary Policy', attempt(1, 1, 3)),
    entry('c', attempts.at(0) || new Date().toISOString(), 'Liquidity', attempt(2, 2, 4)),
    entry('d', attempts.at(0) || new Date().toISOString(), 'Liquidity', null),
  ];
  const totals = computeAccuracyTotals(history);
  assert.strictEqual(totals.sessions, 3);
  assert.strictEqual(totals.answered, 10);
  assert.strictEqual(totals.correct, 6);
  assert.strictEqual(totals.accuracy, 60);
}

// --- computeCurrentStreak --------------------------------------------------
{
  const history = [
    entry('a', attempts.at(0), 'T', attempt(0, 3, 3)),
    entry('b', attempts.at(0), 'T', attempt(1, 3, 3)),
    entry('c', attempts.at(0), 'T', attempt(2, 3, 3)),
  ];
  assert.strictEqual(computeCurrentStreak(history), 3, 'consecutive days = 3');
}

{
  // Gap yesterday → streak survives to the 2-day-old session only if today
  // has practice; here it does not and yesterday is missing → streak == 0.
  const history = [
    entry('a', attempts.at(0), 'T', attempt(0, 3, 3)),
    entry('b', attempts.at(0), 'T', attempt(2, 3, 3)),
  ];
  assert.strictEqual(computeCurrentStreak(history), 1, 'gap breaks streak');
}

{
  // Practiced yesterday but not today yet → streak still counts.
  const history = [
    entry('a', attempts.at(0), 'T', attempt(1, 3, 3)),
    entry('b', attempts.at(0), 'T', attempt(2, 3, 3)),
  ];
  assert.strictEqual(computeCurrentStreak(history), 2, 'yesterday-only streak alive');
}

assert.strictEqual(computeCurrentStreak([]), 0, 'empty history = 0 streak');

// --- computeProgressSummary ------------------------------------------------
{
  const history = [
    entry('a', attempts.at(0), 'Monetary Policy', attempt(0, 4, 5)),
    entry('b', attempts.at(0), 'Fiscal', attempt(1, 2, 5)),
    entry('c', attempts.at(0), 'Monetary Policy', null),
  ];
  const summary = computeProgressSummary(history);
  assert.strictEqual(summary.sessions, 2);
  assert.strictEqual(summary.answered, 10);
  assert.strictEqual(summary.correct, 6);
  assert.strictEqual(summary.accuracy, 60);
  assert.strictEqual(summary.streak, 2);
  assert.strictEqual(summary.saved, 3);
}

// --- computeTopicBreakdown -------------------------------------------------
{
  const history = [
    entry('a', attempts.at(0), 'Monetary Policy', attempt(1, 5, 5)),
    entry('b', attempts.at(0), 'Fiscal', attempt(1, 1, 4)),
    entry('c', attempts.at(0), 'Monetary Policy', attempt(2, 3, 5)),
  ];
  const topics = computeTopicBreakdown(history);
  assert.strictEqual(topics.length, 2);
  // Weakest first
  assert.strictEqual(topics[0].topic, 'Fiscal');
  assert.strictEqual(topics[0].accuracy, 25);
  assert.strictEqual(topics[1].topic, 'Monetary Policy');
  assert.strictEqual(topics[1].accuracy, 80);
  assert.strictEqual(topics[1].sessions, 2);
}

// Attempts without history must not crash; missing topic falls back.
{
  assert.deepStrictEqual(computeTopicBreakdown([]), []);
  const noTopic = entry('z', attempts.at(0), '', attempt(0, 1, 2));
  assert.strictEqual(computeTopicBreakdown([noTopic])[0].topic, 'Economy');
}

// --- computeTopicOptions ---------------------------------------------------
{
  const history = [
    entry('a', attempts.at(0), 'Newest Topic', attempt(0, 1, 1)),
    entry('b', attempts.at(0), 'Old Topic', null),
    entry('c', attempts.at(0), 'Newest Topic', null),
  ];
  assert.deepStrictEqual(computeTopicOptions(history), ['Newest Topic', 'Old Topic']);
}

console.log('All progress.js tests passed');
