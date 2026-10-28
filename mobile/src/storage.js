// NewQ local persistence layer (AsyncStorage).
// Stores exam preference, appearance preference is handled in theme.js usage,
// and a capped list of past analysis sessions for the History tab.

import AsyncStorage from '@react-native-async-storage/async-storage';

export const HISTORY_KEY = 'newq-history';
export const EXAM_KEY = 'newq-exam';
export const SERVER_KEY = 'newq-api-server';
export const MAX_HISTORY = 20;

export function createHistoryEntry(result, exam) {
  return {
    id: `h-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
    createdAt: new Date().toISOString(),
    exam: exam || result?.exam || 'UPSC',
    subject: result?.subject || 'General',
    topic: result?.topic || 'General Current Affairs',
    relevance: result?.relevance || '',
    questionCount: Array.isArray(result?.questions)
      ? result.questions.length
      : 0,
    attempt: null,
    result,
  };
}

export async function loadHistory() {
  try {
    const raw = await AsyncStorage.getItem(HISTORY_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    return [];
  }
}

export async function appendHistory(entry) {
  const history = await loadHistory();
  history.unshift(entry);
  const trimmed = history.slice(0, MAX_HISTORY);
  await AsyncStorage.setItem(HISTORY_KEY, JSON.stringify(trimmed));
  return trimmed;
}

export async function persistAttempt(historyId, correct, answered, total) {
  const history = await loadHistory();
  const index = history.findIndex((entry) => entry.id === historyId);

  if (index === -1) {
    return history;
  }

  const updated = [...history];
  updated[index] = {
    ...updated[index],
    attempt: {
      correct,
      answered,
      total,
      accuracy: total ? Math.round((correct / total) * 100) : 0,
      at: new Date().toISOString(),
    },
  };

  await AsyncStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
  return updated;
}

export async function clearAllHistory() {
  await AsyncStorage.setItem(HISTORY_KEY, JSON.stringify([]));
  return [];
}

export async function saveExamPreference(exam) {
  await AsyncStorage.setItem(EXAM_KEY, exam);
}

export async function loadExamPreference() {
  try {
    return (await AsyncStorage.getItem(EXAM_KEY)) || 'UPSC';
  } catch (error) {
    return 'UPSC';
  }
}

// Stage 7b: user-editable NewQ API server address (survives hotspot IP
// churn — update the PC address in Profile instead of editing api.js).
export async function getServerPreference() {
  try {
    return (await AsyncStorage.getItem(SERVER_KEY)) || '';
  } catch (error) {
    return '';
  }
}

export async function saveServerPreference(url) {
  const trimmed = String(url || '').trim().replace(/\/+$/, '');
  await AsyncStorage.setItem(SERVER_KEY, trimmed);
  return trimmed;
}

export async function clearServerPreference() {
  await AsyncStorage.removeItem(SERVER_KEY);
}
