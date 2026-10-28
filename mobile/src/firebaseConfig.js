// Firebase web configuration — activated 2026-10-27 (project: newq-05-01).
//
// NOTE: A Firebase web apiKey is a public identifier, not a secret —
// security comes from Firestore security rules (see FIREBASE_SETUP.md).
// Never put the Gemini backend key in this file.
//
// Filling apiKey + projectId switches the app from local-only mode to
// cloud sync; the Profile tab shows the live status.

export const firebaseConfig = {
  apiKey: 'AIzaSyDfUxNEjbLOSt5M2nHZjnfp9FY87p0zJUQ',
  authDomain: 'newq-05-01.firebaseapp.com',
  projectId: 'newq-05-01',
  storageBucket: 'newq-05-01.firebasestorage.app',
  messagingSenderId: '829872955726',
  appId: '1:829872955726:web:e0dcfd0f0a3b45e7c77e1f',
};

// Ready to initialize only when the project identifiers exist.
export function isFirebaseConfigured() {
  return Boolean(firebaseConfig.apiKey && firebaseConfig.projectId);
}
