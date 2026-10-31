# Drills on the demo page, and the "?" in drills

Two fixes so the practice attacks can always be shown from the demo page (`/backstage`), and so the n8n "?"
helper works during a drill as well as on the alert screens. **Status: built and verified** (see
the end of this file). No contract change: the backend already accepted what's needed.

## Why it doesn't work today

- **The "?" never appears in a drill.** It was added to the owner home screen (`OwnerNow.jsx`)
  and the staff Today screen (`Staff.jsx`) only. The drill screens (`StaffDrill.jsx`,
  `OwnerDrill.jsx`) don't use `RephraseProvider`. The backend is ready: `POST /interpreter/chat`
  takes `drill_code`, `backend/ai/context.py` turns it into context for the agent (scenario,
  current moment, status), and the event log records it. The frontend just never sends it.
- **The demo page doesn't show the learning drills at all**, and shows the practice attacks only
  when the server runs with `SIMULATE=1`. With no `backend/.env` (it's gitignored), every flag is
  off, so the Attack simulation card disappears without saying why.

## Part 1: the "?" in drills

| # | Change | File |
|---|---|---|
| 1 | `explainCard` sends `drill_code` alongside `alert_id`. One extra field; existing callers don't change | `frontend/src/lib/rephrase.js` |
| 2 | Wrap the staff drill screen in `RephraseProvider` (the player's role, `en`, the drill code). Before answering, the moment's situation can be reworded; after answering, the feedback can be too | `frontend/src/pages/StaffDrill.jsx` |
| 3 | Same on the owner's drill screen, with role `owner`: the situation and the owner's feedback | `frontend/src/pages/OwnerDrill.jsx` |
| 4 | Check the "?" doesn't cover an answer button or the tab bar in the dark full-screen drill look on phones. If it does, raise it on drill screens only | `frontend/src/styles/shieldmate.css` |

**The answer choices are never sent to the agent.** A reworded option could hint at the right
one and spoil the drill, so only the situation and the feedback are offered.

## Part 2: the drills on the demo page

| # | Change | File |
|---|---|---|
| 1 | The **Attack simulation** card is always visible. With `SIMULATE` off, its Play buttons are greyed out with "Start the server with SIMULATE=1 to run practice attacks". With it on, nothing changes, including the "Team sees: Attack stopped in 1:05…" line | `frontend/src/pages/Backstage.jsx` |
| 2 | Create `backend/.env` with `ACTIONS=1`, `SIMULATE=1`, `AI_INTERPRETER=1` and `AI_INTERPRETER_URL` set to the n8n webhook. Local only; it's gitignored | `backend/.env` |

**Left out on purpose:** adding the three new attacks to the old click buttons at the top of
backstage. Those buttons only accept `password_guessing` and `ransomware`, which is fixed in the
contract (`ReplayType`), so it would need another sign-off from all four owners. The Attack
simulation card already does the job, and it also shows who stopped the attack.

## Tests

- Unit (vitest): `drill_code` is sent; the answer choices are never part of the question.
- End to end (Playwright): someone joins a drill, taps "?", ticks the situation and sees
  "In simpler words". Skipped when `AI_INTERPRETER` is off, like the existing n8n story.
- Full run before handing over: backend tests, frontend unit tests, the production build, and
  every end-to-end story with `ACTIONS=1 SIMULATE=1 AI_INTERPRETER=1`. Screenshots of a drill
  phone with the "?", the owner drill screen and the new backstage cards.

## Ownership

All changes are in `frontend/`, Abhiram's lane. The "?" helper was built by Ishaan, who makes
these changes; Abhiram should know about them before the next merge.

## Built (verification)

All of the above is implemented. Backend 439 tests, frontend 64 unit tests, production build, and
all 13 end-to-end stories pass (the backstage one also with `SIMULATE` off). The end-to-end run
blanks `AI_INTERPRETER_URL` so tests never call the live n8n agent. Notes:

- In a drill the "?" offers two cards per moment: the situation, and (after answering) the "why".
  The answer options are never registered, so they can't be sent.
- `explainCard` adds `drill_code` only on drill screens; alert screens send exactly what they did.
- `backend/.env` was created locally (gitignored). `.env.example` is unchanged.
- **Removed (2026-11-01):** a "Team drills" card on backstage that linked each learning drill
  to the owner drill screen. It only navigated away from backstage, which wasn't wanted, and
  didn't match the page. Learning drills are started from the owner screen (`/owner/drill`).
