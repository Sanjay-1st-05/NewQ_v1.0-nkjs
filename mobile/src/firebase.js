// Firebase initialization: anonymous auth + Firestore.
//
// The whole module degrades to nulls when firebaseConfig.js is not filled
// in, so callers can treat "cloud unavailable" as the normal offline path.

import AsyncStorage from '@react-native-async-storage/async-storage';
import { initializeApp, getApps } from 'firebase/app';
import {
  createUserWithEmailAndPassword,
  getAuth,
  initializeAuth,
  getReactNativePersistence,
  onAuthStateChanged,
  signInAnonymously,
  signInWithEmailAndPassword,
  signOut,
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

// Fires with the current user object (or null) and on every auth
// change. Returns an unsubscribe function. When unconfigured it
// immediately reports null so callers fall back to local-only behavior.
export function watchAuth(callback) {
  if (!auth) {
    callback(null);
    return () => {};
  }

  return onAuthStateChanged(auth, (user) => callback(user));
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

// Maps Firebase error codes to short, user-facing login messages.
export function friendlyAuthError(error) {
  const code = error?.code || '';

  switch (code) {
    case 'auth/invalid-credential':
    case 'auth/wrong-password':
    case 'auth/user-not-found':
      return 'Incorrect email or password.';
    case 'auth/email-already-in-use':
      return 'An account with this email already exists. Sign in instead.';
    case 'auth/weak-password':
      return 'Password must be at least 6 characters.';
    case 'auth/invalid-email':
      return 'That email address does not look valid.';
    case 'auth/too-many-requests':
      return 'Too many attempts. Please wait a moment and try again.';
    case 'auth/network-request-failed':
      return 'Network problem. Check your connection and retry.';
    case 'auth/operation-not-allowed':
      return 'Email sign-in is not enabled in the Firebase console yet.';
    case 'auth/user-disabled':
      return 'This account has been disabled.';
    default:
      return error?.message || 'Sign-in failed. Please try again.';
  }
}

// Stage 7: email/password sign-in. Returns {uid, email} on success or
// {error} with a friendly message — callers decide what to render.
export async function signInWithEmailPassword(email, password) {
  if (!auth) {
    return { error: 'Cloud is not configured on this device.' };
  }

  try {
    const credential = await signInWithEmailAndPassword(auth, email, password);
    return {
      uid: credential.user.uid,
      email: credential.user.email,
      isAnonymous: credential.user.isAnonymous,
    };
  } catch (error) {
    lastAuthError = error?.code || error?.message || 'signin-error';
    return { error: friendlyAuthError(error) };
  }
}

// Stage 7: email/password account creation (signs the user in on success).
export async function createAccountWithEmail(email, password) {
  if (!auth) {
    return { error: 'Cloud is not configured on this device.' };
  }

  try {
    const credential = await createUserWithEmailAndPassword(
      auth,
      email,
      password,
    );
    return {
      uid: credential.user.uid,
      email: credential.user.email,
      isAnonymous: false,
    };
  } catch (error) {
    lastAuthError = error?.code || error?.message || 'signup-error';
    return { error: friendlyAuthError(error) };
  }
}

// Stage 7: explicit sign-out. Local history stays on the device; only
// the Firebase session is dropped.
export async function signOutUser() {
  if (!auth || !auth.currentUser) {
    return;
  }
  try {
    await signOut(auth);
  } catch (error) {
    lastAuthError = error?.code || error?.message || 'signout-error';
  }
}
