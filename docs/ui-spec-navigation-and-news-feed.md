# Feature Specification: Navigation Menu (Hamburger) and Login-Day News Feed

## Purpose

User feedback shows two recurring pain points: people cannot reliably find
their profile and settings from the home screen, and exam candidates want to
scan current-affairs headlines the moment they sign in instead of hunting for
the news panel. This specification defines two changes that address both: a
hamburger menu at the top-left corner after login, and an RSS news feed
displayed immediately upon login. Both changes target the existing
application only; no server changes are needed beyond wiring existing
screens and the existing news feed data source.

## Change 1: Hamburger menu (three-bar button)

### Requirements

- A three-bar (hamburger) icon appears at the **top-left corner** of every
  screen immediately after login.
- Tapping it opens a slide-in drawer from the left with three items:

  | Item | Behavior |
  |---|---|
  | Dashboard | Opens the Dashboard — the existing home screen, renamed so the label matches the menu |
  | Profile | Opens the existing Profile screen (account, history entry points) |
  | Settings | Opens a new Settings screen; moves the controls currently behind the top-right gear icon (appearance, API server address) |

- The drawer closes on item tap or background tap.
- The bottom tab bar (Home / History / Profile) stays unchanged; the drawer
  is an addition, not a replacement.

### Wireframe

```
Before (after login)          After (after login)
┌──────────────────────┐      ┌──────────┬───────────────────┐
│                NewQ ⚙│      │ Dashboard│                   │
│                      │      │──────────┤   Dashboard       │
│     Dashboard        │  →   │ Profile  │                   │
│                      │      │ Settings │  ☰ now top-left   │
└──────────────────────┘      └──────────┴───────────────────┘
```

## Change 2: RSS feed shown at login

### Requirements

- Immediately upon login, the Dashboard displays the existing
  current-affairs RSS feed at the **top of the screen**, above the news
  input card.
- Each headline is tappable and opens the article's link.
- While headlines load, show a simple "Loading news…" placeholder; if the
  feed cannot load, show "News is temporarily unavailable — you can still
  analyze your own article" so the core workflow is never blocked.
- Rows must never overlap or push the "Analyze News" action off screen; the
  feed area scrolls independently within the Dashboard.

## What stays the same

No changes to the analysis flow, question generation, history, or profile
features. The gear icon moves into Settings; it is removed from the top right
to avoid two entry points for the same controls.

## Expected outcomes

- Settings reachable within two taps from any screen; today they sit behind
  a small icon that feedback says users fail to notice.
- Candidates see exam-relevant headlines on arrival, giving the app a daily
  open reason even before practicing.
- The rename to Dashboard plus a visible menu resolves the Home-vs-Profile
  ambiguity the feedback flagged.

## Suggestions (not required)

- A subtle slide transition for the drawer.
- Remembering the drawer's last-opened item state between sessions.

These are quality touches; implement them only if they cost no extra
schedule. All four outcomes above depend solely on the two required changes.
