// Firestore sync for NewQ history sessions.
//
// Data model: users/{uid}/sessions/{entryId} — one document per saved
// analysis. All functions no-op and resolve cleanly when Firestore is not
// available (unconfigured or offline), so local storage stays the source
// of truth and the cloud is a best-effort mirror.

import {
  collection,
  getDocs,
  limit,
  onSnapshot,
  orderBy,
  query,
  setDoc,
  writeBatch,
} from 'firebase/firestore';
import { db } from './firebase';

function sessionDoc(uid, entryId) {
  if (!db || !uid || !entryId) {
    return null;
  }
  return doc(db, 'users', uid, 'sessions', entryId);
}

// Create or replace one history entry document.
export async function cloudPushEntry(uid, entry) {
  const ref = uid && entry?.id ? sessionDoc(uid, entry.id) : null;

  if (!ref) {
    return false;
  }

  try {
    await setDoc(ref, entry);
    return true;
  } catch (error) {
    return false;
  }
}

// Merge an attempt score into an existing session document.
export async function cloudUpdateAttempt(uid, entryId, attempt) {
  const ref = sessionDoc(uid, entryId);

  if (!ref) {
    return false;
  }

  try {
    await setDoc(ref, { attempt }, { merge: true });
    return true;
  } catch (error) {
    return false;
  }
}

// Newest-first snapshot of the user's sessions (capped like local history).
// Returns an unsubscribe function; null when the cloud is unavailable.
export function cloudSubscribeHistory(uid, onData, onError) {
  if (!db || !uid) {
    return null;
  }

  const recent = query(
    collection(db, 'users', uid, 'sessions'),
    orderBy('createdAt', 'desc'),
    limit(50),
  );

  return onSnapshot(
    recent,
    (snapshot) => onData(snapshot.docs.map((entry) => entry.data())),
    (error) => onError?.(error),
  );
}

// Delete every session document for the user (mirrors clear-all).
export async function cloudClearHistory(uid) {
  if (!db || !uid) {
    return false;
  }

  try {
    const snapshot = await getDocs(
      collection(db, 'users', uid, 'sessions'),
    );
    const batch = writeBatch(db);
    snapshot.docs.forEach((entry) => batch.delete(entry.ref));
    await batch.commit();
    return true;
  } catch (error) {
    return false;
  }
}
