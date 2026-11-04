// NewQ Stage 8a — progress computation for the History screen.
//
// Pure functions only (no React, no storage imports) so the logic can be
// unit-tested directly in Node. Inputs are history entries in the shape
// produced by storage.createHistoryEntry / persistAttempt:
//   { id, createdAt, exam, subject, topic, questionCount,
//     attempt: { correct, answered, total, accuracy, at } | null, result }
//
// A practice day is a calendar day (local time) with at least one attempt.
// The streak counts consecutive such days ending today or yesterday.

function dayKey(timestamp) {
  const date = timestamp instanceof Date ? timestamp : new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function computeCurrentStreak(history, now = new Date()) {
  const days = new Set();

  (Array.isArray(history) ? history : []).forEach((entry) => {
    if (entry?.attempt?.at) {
      const key = dayKey(entry.attempt.at);
      if (key) {
        days.add(key);
      }
    }
  });

  if (days.size === 0) {
    return 0;
  }

  // Walk back from today; the streak survives if the most recent practice
  // day is yesterday (user has not practiced yet today).
  let streak = 0;
  const cursor = new Date(now.getFullYear(), now.getMonth(), now.getDate());

  if (!days.has(dayKey(cursor))) {
    cursor.setDate(cursor.getDate() - 1);
    if (!days.has(dayKey(cursor))) {
      return 0;
    }
  }

  while (days.has(dayKey(cursor))) {
    streak += 1;
    cursor.setDate(cursor.getDate() - 1);
  }

  return streak;
}

// Percent (0-100) across every attempted question, computed from raw
// correct/answered counts so per-entry rounding never skews the total.
export function computeAccuracyTotals(history) {
  let answered = 0;
  let correct = 0;
  let sessions = 0;

  (Array.isArray(history) ? history : []).forEach((entry) => {
    const attempt = entry?.attempt;
    if (!attempt) {
      return;
    }
    sessions += 1;
    answered += attempt.answered || attempt.total || 0;
    correct += attempt.correct || 0;
  });

  return {
    sessions,
    answered,
    correct,
    accuracy: answered ? Math.round((correct / answered) * 100) : null,
  };
}

export function computeProgressSummary(history, now = new Date()) {
  const totals = computeAccuracyTotals(history);

  return {
    ...totals,
    streak: computeCurrentStreak(history, now),
    saved: Array.isArray(history) ? history.length : 0,
  };
}

// Per-topic roll-up over sessions that have been attempted. Sorted by
// average accuracy ascending so weak topics surface first.
export function computeTopicBreakdown(history) {
  const byTopic = new Map();

  (Array.isArray(history) ? history : []).forEach((entry) => {
    const attempt = entry?.attempt;
    if (!attempt) {
      return;
    }
    const topic = topicLabel(entry);
    const current = byTopic.get(topic) || {
      topic,
      sessions: 0,
      correct: 0,
      answered: 0,
    };

    current.sessions += 1;
    current.correct += attempt.correct || 0;
    current.answered += attempt.answered || attempt.total || 0;
    byTopic.set(topic, current);
  });

  return [...byTopic.values()]
    .map((item) => ({
      ...item,
      accuracy: item.answered
        ? Math.round((item.correct / item.answered) * 100)
        : 0,
    }))
    .sort((a, b) => a.accuracy - b.accuracy || a.topic.localeCompare(b.topic));
}

// Topics available for the filter chips: every topic that exists in the
// saved history, practiced or not, newest-first order of first appearance.
export function computeTopicOptions(history) {
  const seen = new Set();
  const options = [];

  (Array.isArray(history) ? history : []).forEach((entry) => {
    const label = topicLabel(entry);
    if (!seen.has(label)) {
      seen.add(label);
      options.push(label);
    }
  });

  return options;
}

function topicLabel(entry) {
  return entry?.topic || entry?.subject || 'General';
}
