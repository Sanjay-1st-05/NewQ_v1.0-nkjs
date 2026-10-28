// Firebase initialization: anonymous auth + Firestore.
//
// The whole module degrades to nulls when firebaseConfig.js is not filled
// in, so callers can treat "cloud unavailable" as the normal offline path.

import AsyncStorage from '@react-native-async-storage/async-storage';
import { initializeApp, getApps } from 'firebase/app';
import {
  getAuth,
  initializeAuth,
  getReactNativePersistence,
  onAuthStateChanged,
  signInAnonymously,
} from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';
import { firebaseConfig, isFirebaseConfigured } from './firebaseConfig';

let auth = null;
let db = null;
let lastAuthError = null;

if (isFirebaseConfigured()) {
  const app = getApps().length ? getApps()[0] : initializeApp(firebaseConfig);

  try {
    // AsyncStorage persistence keeps the anonymous session across app
    // restarts; the uid stays stable on the same device.
    auth = initializeAuth(app, {
      persistence: getReactNativePersistence(AsyncStorage),
    });
  } catch (error) {
    // Already initialized (Fast Refresh / hot reload): getAuth returns
    // the existing instance instead of re-initializing.
    auth = getAuth(app);
  }

  db = getFirestore(app);
}

export function isCloudEnabled() {
  return Boolean(db);
}

export function getAuthError() {
  return lastAuthError;
}

// Resolves to a uid, or null when sign-in fails (offline, bad config,
// anonymous auth not enabled yet). Null means "local-only mode".
export async function ensureSignedIn() {
  if (!auth) {
    return null;
  }

  try {
    const credential = await signInAnonymously(auth);
    return credential.user?.uid || null;
  } catch (error) {
    lastAuthError = error?.code || error?.message || 'auth-error';
    return null;
  }
}

// Fires with the current uid (or null) and on every auth change.
// Returns an unsubscribe function. When unconfigured it immediately
// reports null so callers fall back to local-only behavior.
export function watchAuth(callback) {
  if (!auth) {
    callback(null);
    return () => {};
  }

  return onAuthStateChanged(auth, (user) => callback(user?.uid || null));
}

// Stage 7: resolves a current Firebase ID token for API authorization.
// Signs in anonymously first when there is no session yet. Resolves to
// null in local-only mode (unconfigured) or on any failure, so callers
// degrade gracefully to "request without auth header".
export async function getFirebaseAuthToken() {
  if (!auth) {
    return null;
  }

  try {
    if (!auth.currentUser) {
      await ensureSignedIn();
    }

    if (!auth.currentUser) {
      return null;
    }

    // Auto-refreshes when close to expiry (Firebase handles the 1h TTL).
    return await auth.currentUser.getIdToken();
  } catch (error) {
    lastAuthError = error?.code || error?.message || 'token-error';
    return null;
  }
}
