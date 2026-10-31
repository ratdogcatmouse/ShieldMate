# Abhiram: attack notification button

What the frontend has to deliver for the attack notifications with a quick-action button.
Background and the backend half (Ishaan, Cetas) are in [peaceful-doodling-tulip.md](peaceful-doodling-tulip.md), Feature 2.

## What you're building

When a new attack alert arrives, the relevant staff (the device's account role, plus the owner) get a
notification on their phone. For a password-guessing attack it carries a one-tap button, for example
**"Block 192.168.1.57 for 60 minutes"**. Tapping it approves the existing `BLOCK_IP` action, so there is no new
route and no push notification (Web Push doesn't work on the LAN demo rig).

## What Ishaan hands you first

Build against these once they are merged; don't wait for the live backend.

- The final `QuickAction` shape in `backend/contract.py`.
- `backend/fixtures/notifications.json` (now has `kind` and `quick_action: null`) and the new
  `backend/fixtures/notification_attack.json`.
- A stack that runs with `ACTIONS=1` (the button only exists when ACTIONS is on).

## Response shape you consume

`GET /api/notifications?role=...&staff_id=...&since_id=...` returns two new fields on each notification:

- `kind`: `"info"` or `"attack"`.
- `quick_action`: `null`, or the object below.

```json
{
  "id": 7,
  "kind": "attack",
  "alert_id": 12,
  "action_row_id": 4,
  "to_role": "front_desk",
  "text": "Someone is repeatedly guessing the password on RECEPTION-PC.",
  "created_at": "2026-11-01T04:11:05Z",
  "quick_action": {
    "action_row_id": 4,
    "action": "BLOCK_IP",
    "label": "Block 192.168.1.57 for 60 minutes",
    "target_ip": "192.168.1.57",
    "minutes": 60,
    "status": "proposed"
  }
}
```

The field name `action_row_id` (rather than `action_id`) is pending Ishaan's confirmation. It is the **row id of
the action**, the value you pass to `approve`. It is not the string `"BLOCK_IP"`.

## Checklist

### Staff phones
- [ ] Poll notifications on the staff pages. Today only `OwnerNotify.jsx`, `OwnerNow.jsx` and `Mission.jsx` call
      `api.getNotifications`; [Staff.jsx](../frontend/src/pages/Staff.jsx) does not, and attack notes go to
      `front_desk` and `billing` too. Use `usePoll` with `getNotifications(role, staffId, sinceId)`.
- [ ] Keep the `last_id` cursor. When the server's `last_id` drops below the stored cursor (a Reset), start
      again from 0.

### The notification row
- [ ] Style `kind === "attack"` differently from `info` (the plan says dim/mark it).
- [ ] Render `text` as a plain text node only. Never `dangerouslySetInnerHTML`.
- [ ] Show the button only when `quick_action` is non-null **and** `quick_action.status === "proposed"`.
      A null `quick_action` (no source IP, ACTIONS off, or a refused proposal) means no button and no error.
- [ ] Button label comes from `quick_action.label`; don't build it on the client.

### The tap
- [ ] Call the existing `api.approve(quick_action.action_row_id, thisPhoneStaffId)`
      ([api.js](../frontend/src/lib/api.js)). The staff id comes from the `/staff/:id` route.
- [ ] Disable the button while the request is in flight (`useAction` in `components/ui.jsx`).
- [ ] On success call `refresh()` so the next poll shows the new status.
- [ ] On a 409 `action_not_pending` (someone already answered), treat it as handled: re-poll and show the
      resulting state, not an error.

### States the row has to render

| `quick_action` | Row shows |
|---|---|
| `null` | The note only, no button |
| `status: "proposed"` | Active button |
| `status: "executed"` | Disabled button, "Blocked" |
| `status: "expired"` | Disabled button, "Block ended" |
| any other status (`declined`, `withdrawn`, ...) | Disabled, no button; the backend only attaches the three above |

### Owner phone
- [ ] [OwnerNotify.jsx](../frontend/src/pages/OwnerNotify.jsx) already builds its own "Block an attacker?" card
      from `/actions` and shows `notes.slice(-2)` as plain text. An owner attack note would show the same thing
      twice. Pick one: hide attack notes that match a pending action, or render that card from the note.

### Housekeeping
- [ ] `backend/.env.example` has `ACTIONS=0`. Document that the notification demo needs `ACTIONS=1`.
- [ ] Tests: vitest for the state rendering and the cursor reset, Playwright for tap -> disabled.
      `make test` and `make e2e` (the e2e needs the `ACTIONS=1` stack running) must stay green.

## Open questions for you

1. Do you want `expires_at` in `QuickAction`? The plan only has `minutes`, but `OwnerNotify.jsx` currently shows
   "protected until 4:15". Without it the executed state can only say "Blocked".
2. PIN: `POST /actions/{id}/approve` only has the PIN check, which is off today, so a staff tap works. Once
   `OWNER_PIN` is set, staff taps return 401 `pin_required`. Is that acceptable, or should staff taps send a PIN?

## Done when

1. Start the stack with `ACTIONS=1` and press Reset.
2. Replay the rule 60204 password-guessing attack from Backstage. This is the attack that has a source IP;
   ransomware has none, so it shows no button.
3. The front-desk phone shows an attack notification with the button.
4. Tap it: the action goes to `executed` and the button disables.
5. The owner phone shows the note without a duplicate approval card.
