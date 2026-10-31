// Presentation-only content: friendly names, labels and on-screen wording that the API doesn't
// carry. Alert text, steps, drill situations and options all come from the backend
// (lessons.json, scenarios/*.json); nothing here decides what anyone should do.

export const ROLE_LABEL = { front_desk: "Front desk", billing: "Billing", owner: "Owner" };

// Devices by Wazuh agent name. Unknown agents fall back to the agent name itself.
export const DEVICE_NAMES = {
  "RECEPTION-PC": { name: "Reception computer", short: "Reception" },
  "FILE-SERVER": { name: "File server", short: "File server" },
  "DOCTOR-PC": { name: "Doctor's computer", short: "Doctor's computer" },
};
export const deviceName = (agent) => DEVICE_NAMES[agent]?.name ?? agent;
export const deviceShort = (agent) => DEVICE_NAMES[agent]?.short ?? agent;

// Device strip states: the API's own (ok, under_attack, protected), plus the ones the screens
// work out from open alerts or a drill step's story (files_locked, isolated, infected, ...).
export const DEVICE_STATUS = {
  ok: { label: "OK", tone: "green" },
  under_attack: { label: "Under attack", tone: "red" },
  protected: { label: "Protected", tone: "blue" },
  files_locked: { label: "Files locked", tone: "red" },
  isolated: { label: "Cut off, still on", tone: "amber" },
  infected: { label: "Infected", tone: "red" },
  encrypting: { label: "Files locking", tone: "red" },
  encrypted: { label: "Files locked", tone: "red" },
};

// What each action ID means, for "Remember these" after a drill.
export const ACTION_LABEL = {
  DONT_USE_DEVICE: "Stop using the affected computer",
  ISOLATE_NETWORK: "Unplug the network, leave the computer on",
  CALL_SAVED_IT: "Only call numbers saved in ShieldMate",
  NOTIFY_OWNER: "Tell the owner",
  PRESERVE_EVIDENCE: "Write down what you saw and when",
  VERIFY_BACKUP: "Test the backup before restoring",
  REPORT_CERTIN: "Report to CERT-In within 6 hours",
  START_DPDP_NOTE: "Start the patient-data breach record",
  BLOCK_IP: "Block the attacking address",
};

// The staff card's buttons and headings. Kannada and Hindi are DRAFTS: a fluent speaker must
// check them (Testing Plan T2.05). The card text itself comes from the server.
export const UI_TEXT = {
  en: { needs: "Needs you now", handled: "Handled", paused: "Paused", doThese: "Do these now", of: "of", done: "done", why: "Why it matters:", details: "Details from the computer's log", tell: "I've done these · tell Dr. Rao", mine: "That was me: I mistyped my password", call: "Call" },
  kn: { needs: "ಈಗ ನಿಮ್ಮ ಅಗತ್ಯವಿದೆ", handled: "ನಿರ್ವಹಿಸಲಾಗಿದೆ", paused: "ವಿರಾಮ", doThese: "ಈಗ ಇವುಗಳನ್ನು ಮಾಡಿ", of: "/", done: "ಮುಗಿದಿದೆ", why: "ಇದು ಏಕೆ ಮುಖ್ಯ:", details: "ಕಂಪ್ಯೂಟರ್ ಲಾಗ್‌ನ ವಿವರಗಳು", tell: "ಇವುಗಳನ್ನು ಮಾಡಿದ್ದೇನೆ · ಡಾ. ರಾವ್‌ಗೆ ತಿಳಿಸಿ", mine: "ಅದು ನಾನೇ: ಪಾಸ್‌ವರ್ಡ್ ತಪ್ಪಾಗಿ ಟೈಪ್ ಮಾಡಿದೆ", call: "ಕರೆ ಮಾಡಿ" },
  hi: { needs: "अभी आपकी ज़रूरत है", handled: "संभाल लिया गया", paused: "रुका हुआ", doThese: "अभी ये करें", of: "/", done: "पूरे", why: "यह क्यों ज़रूरी है:", details: "कंप्यूटर लॉग का विवरण", tell: "मैंने ये कर लिया · डॉ. राव को बताएँ", mine: "यह मेरी गलती थी: मैंने पासवर्ड गलत टाइप किया", call: "कॉल करें" },
};
export const LANGS = [
  ["en", "EN", "English"],
  ["kn", "ಕ", "Kannada"],
  ["hi", "हि", "Hindi"],
];

// Log field names as the staff and IT screens label them.
export const LOG_FIELD_LABEL = {
  username_tried: "Username tried, exactly as recorded",
  source_ip: "Attacking address",
};

// --- drills ---

export const PHASE_LABEL = { detect: "Spot it", contain: "Contain it", recover: "Recover", report: "Report it" };

// A two-word name for each moment, for progress lists and the projector.
export const STEP_SHORT = {
  ransomware_clinic: { s1: "Files locking", s2: "Fake IT number", s3: "The backup", s4: "Patient records" },
  password_guessing: { s1: "Wrong passwords", s2: "Same address" },
};
export const stepShort = (scenarioId, step) =>
  STEP_SHORT[scenarioId]?.[step.step_id] ?? PHASE_LABEL[step.phase];

// The scenarios the owner can start. "minutes" is a rough guide for the start screen.
export const SCENARIOS = [
  { id: "ransomware_clinic", title: "Ransomware at the clinic", minutes: 6 },
  { id: "password_guessing", title: "Someone is guessing a password", minutes: 3 },
];

// SAMPLE DATA for the retest reveal: last month's ransomware drill. Always labelled
// "sample data" on screen; replace with a real earlier run when there is one.
export const PREVIOUS_DRILL = {
  label: "Last month",
  seeded: true,
  scenario_id: "ransomware_clinic",
  team_right: 5,
  team_total: 10,
};

// --- alerts: owner and IT extras ---

// CERT-In expects a report within 6 hours of noticing a ransomware incident.
export const CERTIN_HOURS = { ransomware: 6 };

// What the clinic's IT contact sees as a suggested fix (a reminder list, not tracked).
export const IT_PLAYBOOK = {
  password_guessing: [
    "Find the device at the attacking address on the clinic network (router's client list)",
    "Change the password of every account that was tried, starting with administrator",
    "Turn on account lockout after 5 wrong passwords on the reception computer",
    "Check the reception computer's sign-ins for any that succeeded",
  ],
  ransomware: [
    "Keep the file server and reception computer off the network; don't switch them off",
    "Identify the ransomware from the note and file extension (don't contact the attackers)",
    "Restore from the last backup that passed ShieldMate's restore check, onto a cleaned machine",
    "Change all clinic passwords and remove the always-plugged-in backup drive",
  ],
};

// Wazuh rule descriptions for the IT panel's technical details.
export const RULE_DESC = {
  "60204": "multiple failed Windows logons",
  "100201": "mass file changes (ransomware pattern)",
  "61320": "phishing email flagged",
};

export const TIP_OF_THE_WEEK =
  "If a pop-up or note gives you a phone number for \"IT support\", don't call it. Only use the contact saved in ShieldMate.";
