# NewQ — Firebase Cloud Sync Setup (dev step 5)

The mobile app already contains the full sync implementation
(`src/firebase.js`, `src/cloud.js`). It runs in **local-only mode** until
you create a Firebase project and paste its web config. Nothing needs to
be mocked: sync activates with your real project in ~5 minutes.

## 1. Create the Firebase project

1. Go to <https://console.firebase.google.com/> → **Add project**
2. Name it (e.g. `newq-app`) — Google Analytics optional, disable if asked

## 2. Register a Web app and copy the config

1. Project overview → the **`</>`** (Web) icon
2. Nickname: `NewQ mobile` → **Register app** (no hosting)
3. From the shown `firebaseConfig` snippet, copy:
   - `apiKey`
   - `authDomain`
   - `projectId`
   - `storageBucket`
   - `messagingSenderId`
   - `appId`
4. Paste them into **`mobile/src/firebaseConfig.js`** (replace the empty
   strings). This file is a *public identifier*, not a secret — safe to
   commit. Never put the Gemini backend key there.

## 3. Enable Anonymous Authentication

1. Console → **Build → Authentication → Get started**
2. **Sign-in method → Anonymous → Enable → Save**

The app signs users in silently; no login screen is needed.

## 4. Create the Firestore database

1. Console → **Build → Firestore Database → Create database**
2. Choose a region (e.g. `asia-south1` for India)
3. Start in **production mode**

## 5. Publish security rules

Firestore → **Rules** → replace with:

```
rules_version = '2';

service cloud.firestore {
  match /databases/{database}/documents {
    // Each anonymous user can touch only their own session documents.
    match /users/{uid}/sessions/{sessionId} {
      allow read, write: if request.auth != null
                         && request.auth.uid == uid;
    }
  }
}
```

→ **Publish**. Without these rules the default (deny-all) rules will
block sync and the app stays local-only.

## 6. Verify on device

Reload the app in Expo Go, then open **Profile**:

- 🟢 **"Syncing · signed in anonymously"** — cloud is live
- 🟡 *Connecting…* — wait a moment
- ⚪ *Cloud off* — `firebaseConfig.js` still empty
- 🔴 *Sign-in failed* — check Anonymous auth is enabled; the app keeps
  working from local storage meanwhile

Then: analyze a news article → open the app on another device with the
same build → the analysis should appear in **History** there too.

## How the sync works (implementation notes)

| Path | Behavior |
|---|---|
| Analyze success | Saved to AsyncStorage first, then mirrored to `users/{uid}/sessions/{id}` (fire-and-forget, never blocks the analysis flow) |
| Quiz completed | Attempt score merged into the same cloud document |
| Cloud snapshot | Live listener; merged with local entries **union-by-id**, newest first, capped at 20 — local remains source of truth while offline |
| Offline entries | Anything local but missing from the cloud is pushed back automatically when connectivity returns |
| Clear history | Deletes both local storage and the cloud session collection |
| Undoing sync | Not supported — clearing is destructive on both stores |

**Data collected:** only NewQ analysis sessions (topic, subject, exam,
questions, source text, attempts) under the anonymous uid. No personal
data, no credentials. Delete the Firebase project to remove everything.
