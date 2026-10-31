/* ShieldMate demo data: clinic seed, lessons, drill scenario, replay alerts.
   Mirrors seed/clinic.json, lessons/lessons.json, scenarios/ransomware_clinic.json
   and replay/alerts.json from the Software Design. All names are fictional. */
(function () {
  "use strict";

  const SEED = {
    clinic: {
      name: "Sunrise Family Clinic",
      backup_age_limit_hours: 24,
      it_contact: { name: "Suresh (CareIT)", phone: "+910000000000" },
      standing_rule: { on: true, set_by: "Dr. Rao", set_at: "14 Oct" },
      approval_timeout_minutes: 5,
      block_minutes: 60,
      never_block: ["192.168.1.1", "192.168.1.20"]
    },
    staff: [
      { id: "meena", name: "Meena", role: "front_desk", role_label: "Front desk", can_restore: false, can_approve: false },
      { id: "ravi", name: "Ravi", role: "billing", role_label: "Billing", can_restore: false, can_approve: false },
      { id: "rao", name: "Dr. Rao", role: "owner", role_label: "Owner", can_restore: true, can_approve: true }
    ],
    devices: [
      { id: "reception", agent: "RECEPTION-PC", name: "Reception computer", short: "Reception", services: ["Front-desk check-in"], status: "ok" },
      { id: "file-server", agent: "FILE-SERVER", name: "File server", short: "File server", services: ["Appointments", "Billing", "Patient records"], status: "ok" },
      { id: "doctor", agent: "DOCTOR-PC", name: "Doctor's computer", short: "Doctor's computer", services: ["Consultations"], status: "ok" }
    ]
  };

  const DEVICE_STATUS = {
    ok: { label: "OK", tone: "green" },
    under_attack: { label: "Under attack", tone: "red" },
    protected: { label: "Protected", tone: "blue" },
    files_locked: { label: "Files locked", tone: "red" },
    isolated: { label: "Cut off, still on", tone: "amber" },
    infected: { label: "Infected", tone: "red" },
    encrypting: { label: "Files locking", tone: "red" },
    encrypted: { label: "Files locked", tone: "red" }
  };

  const ACTIONS = {
    DONT_USE_DEVICE: "Stop using the affected computer",
    ISOLATE_NETWORK: "Unplug the network, leave the computer on",
    CALL_SAVED_IT: "Only call numbers saved in ShieldMate",
    NOTIFY_OWNER: "Tell the owner",
    PRESERVE_EVIDENCE: "Write down what you saw and when",
    VERIFY_BACKUP: "Test the backup before restoring",
    DECIDE_PAYMENT: "Payment is the owner's decision, after talking to IT",
    REPORT_CERTIN: "Report to CERT-In within 6 hours",
    START_DPDP_NOTE: "Start the patient-data breach record",
    BLOCK_IP: "Block the attacking address"
  };

  // Lessons: rules decide the text; numbers are filled from the alert.
  // Kannada and Hindi are DRAFTS: a fluent speaker must check them (Testing Plan T2.05).
  const LESSONS = {
    "60204": {
      lesson_id: "password_guessing",
      severity: "needs_you_now",
      device: "reception",
      drill_scenario: "password_guessing",
      proposed_action: "BLOCK_IP",
      staff: {
        en: {
          headline: "Someone is guessing the password on the reception computer.",
          known: "{count} wrong passwords in {window} minutes. Nobody has got in yet.",
          why: "One right guess opens patient records.",
          steps: [
            { action: "DONT_USE_DEVICE", text: "Don't log in from the reception computer. Use the billing desk for now." },
            { action: "CALL_SAVED_IT", text: "Call your IT contact. Only use the number saved here.", call: true },
            { action: "PRESERVE_EVIDENCE", text: "Keep a note of anything odd you noticed." }
          ]
        },
        kn: {
          headline: "ಯಾರೋ ರಿಸೆಪ್ಷನ್ ಕಂಪ್ಯೂಟರ್‌ನ ಪಾಸ್‌ವರ್ಡ್ ಊಹಿಸಲು ಪ್ರಯತ್ನಿಸುತ್ತಿದ್ದಾರೆ.",
          known: "{window} ನಿಮಿಷಗಳಲ್ಲಿ {count} ತಪ್ಪು ಪಾಸ್‌ವರ್ಡ್‌ಗಳು. ಇನ್ನೂ ಯಾರೂ ಒಳಗೆ ಬಂದಿಲ್ಲ.",
          why: "ಒಂದು ಸರಿಯಾದ ಊಹೆ ರೋಗಿಗಳ ದಾಖಲೆಗಳನ್ನು ತೆರೆಯಬಹುದು.",
          steps: [
            { action: "DONT_USE_DEVICE", text: "ರಿಸೆಪ್ಷನ್ ಕಂಪ್ಯೂಟರ್‌ನಿಂದ ಲಾಗಿನ್ ಮಾಡಬೇಡಿ. ಸದ್ಯಕ್ಕೆ ಬಿಲ್ಲಿಂಗ್ ಡೆಸ್ಕ್ ಬಳಸಿ." },
            { action: "CALL_SAVED_IT", text: "ನಿಮ್ಮ IT ಸಂಪರ್ಕಕ್ಕೆ ಕರೆ ಮಾಡಿ. ಇಲ್ಲಿ ಉಳಿಸಿರುವ ಸಂಖ್ಯೆಯನ್ನು ಮಾತ್ರ ಬಳಸಿ.", call: true },
            { action: "PRESERVE_EVIDENCE", text: "ನೀವು ಗಮನಿಸಿದ ಯಾವುದೇ ವಿಚಿತ್ರ ವಿಷಯವನ್ನು ಬರೆದಿಟ್ಟುಕೊಳ್ಳಿ." }
          ]
        },
        hi: {
          headline: "कोई रिसेप्शन कंप्यूटर का पासवर्ड अंदाज़े से खोलने की कोशिश कर रहा है।",
          known: "{window} मिनट में {count} गलत पासवर्ड। अभी तक कोई अंदर नहीं आ पाया है।",
          why: "एक भी सही अंदाज़ा मरीज़ों के रिकॉर्ड खोल सकता है।",
          steps: [
            { action: "DONT_USE_DEVICE", text: "रिसेप्शन कंप्यूटर पर लॉग इन न करें। अभी बिलिंग डेस्क का उपयोग करें।" },
            { action: "CALL_SAVED_IT", text: "अपने IT संपर्क को कॉल करें। केवल यहाँ सेव किया गया नंबर ही इस्तेमाल करें।", call: true },
            { action: "PRESERVE_EVIDENCE", text: "आपने जो भी अजीब देखा, उसे लिख लें।" }
          ]
        }
      },
      owner: {
        headline: "Someone is guessing passwords on the reception computer.",
        known: "{count} wrong passwords from {ip} in {window} minutes.",
        checklist: [
          { action: "DONT_USE_DEVICE", text: "Staff stop using the reception computer" },
          { action: "CALL_SAVED_IT", text: "Call the saved IT contact" },
          { action: "BLOCK_IP", text: "Decide whether to block the attacking address" }
        ]
      }
    },
    "100201": {
      lesson_id: "ransomware",
      severity: "needs_you_now",
      device: "file-server",
      drill_scenario: "ransomware_clinic",
      proposed_action: null,
      certin_hours: 6,
      staff: {
        en: {
          headline: "Files on the file server are being locked. This looks like ransomware.",
          known: "{files} files renamed to \".locked\" in 1 minute.",
          why: "Every minute it stays connected, it can lock more of the clinic's files.",
          steps: [
            { action: "ISOLATE_NETWORK", text: "Unplug your computer's network cable or turn Wi-Fi off. Leave it switched on." },
            { action: "CALL_SAVED_IT", text: "Call your IT contact. Ignore any number in a ransom note.", call: true },
            { action: "NOTIFY_OWNER", text: "Don't touch the backup drive. Tell Dr. Rao." }
          ]
        }
      },
      owner: {
        headline: "Ransomware is locking files on the file server.",
        known: "{files} files renamed to \".locked\" in one minute, and a ransom note was left in the shared folder. Appointments, billing and patient records are down. Use the paper appointment book for now.",
        checklist: [
          { action: "ISOLATE_NETWORK", text: "Cut affected computers off the network, leave them on" },
          { action: "CALL_SAVED_IT", text: "Call the saved IT contact, not the number in the note" },
          { action: "VERIFY_BACKUP", text: "Test the backup before restoring anything", button: "restore" },
          { action: "DECIDE_PAYMENT", text: "Decide on paying: never the front desk's call. Talk to IT first", manual: true },
          { action: "START_DPDP_NOTE", text: "Start the patient-data breach record", manual: true }
        ]
      }
    }
  };

  const UI_TEXT = {
    en: { needs: "Needs you now", handled: "Handled", doThese: "Do these now", of: "of", done: "done", why: "Why it matters:", details: "Details from the computer's log", tell: "I've done these · tell Dr. Rao", mine: "That was me: I mistyped my password", call: "Call" },
    kn: { needs: "ಈಗ ನಿಮ್ಮ ಅಗತ್ಯವಿದೆ", handled: "ನಿರ್ವಹಿಸಲಾಗಿದೆ", doThese: "ಈಗ ಇವುಗಳನ್ನು ಮಾಡಿ", of: "/", done: "ಮುಗಿದಿದೆ", why: "ಇದು ಏಕೆ ಮುಖ್ಯ:", details: "ಕಂಪ್ಯೂಟರ್ ಲಾಗ್‌ನ ವಿವರಗಳು", tell: "ಇವುಗಳನ್ನು ಮಾಡಿದ್ದೇನೆ · ಡಾ. ರಾವ್‌ಗೆ ತಿಳಿಸಿ", mine: "ಅದು ನಾನೇ: ಪಾಸ್‌ವರ್ಡ್ ತಪ್ಪಾಗಿ ಟೈಪ್ ಮಾಡಿದೆ", call: "ಕರೆ ಮಾಡಿ" },
    hi: { needs: "अभी आपकी ज़रूरत है", handled: "संभाल लिया गया", doThese: "अभी ये करें", of: "/", done: "पूरे", why: "यह क्यों ज़रूरी है:", details: "कंप्यूटर लॉग का विवरण", tell: "मैंने ये कर लिया · डॉ. राव को बताएँ", mine: "यह मेरी गलती थी: मैंने पासवर्ड गलत टाइप किया", call: "कॉल करें" }
  };

  // Drill scenario: Software Design, Appendix A.
  const SCENARIOS = {
    ransomware_clinic: {
      scenario_id: "ransomware_clinic",
      title: "Ransomware at the clinic",
      minutes: 6,
      steps: [
        {
          step_id: "s1", phase: "detect", phase_label: "Spot it", game_time: "9:10 AM",
          short: "Files locking",
          situation: "Files on the shared drive are turning into \".locked\" and a ransom note just appeared on the reception computer.",
          devices: { reception: "infected", "file-server": "encrypting" },
          options: {
            staff: [
              { option_id: "a", text: "Switch the computer off", actions: [], correct: false, feedback: "Switching off can wipe evidence investigators need. Unplug the network cable first; only power off if you can't disconnect (CISA)." },
              { option_id: "b", text: "Unplug the network cable or turn Wi-Fi off, and leave the computer on", actions: ["ISOLATE_NETWORK"], correct: true, feedback: "Cutting the network stops the attack spreading to other computers, and keeps the evidence." },
              { option_id: "c", text: "Keep working and tell IT at lunch", actions: [], correct: false, feedback: "Every minute it stays connected, it can lock more of the clinic's files." }
            ],
            owner: []
          }
        },
        {
          step_id: "s2", phase: "contain", phase_label: "Contain it", game_time: "9:14 AM",
          short: "Fake IT number",
          situation: "The ransom note lists an \"IT support\" phone number and a payment link.",
          devices: { reception: "isolated", "file-server": "encrypted" },
          options: {
            staff: [
              { option_id: "a", text: "Call the number in the note", actions: [], correct: false, feedback: "Attackers plant fake helplines. Only use contacts saved in ShieldMate." },
              { option_id: "b", text: "Call the saved IT contact and tell the owner", actions: ["CALL_SAVED_IT", "NOTIFY_OWNER"], correct: true, feedback: "Saved contacts only, and the owner needs to know now." },
              { option_id: "c", text: "Pay quickly to keep the clinic running", actions: [], correct: false, feedback: "Paying is the owner's decision, never the front desk's, and it doesn't guarantee your files come back." }
            ],
            owner: []
          }
        },
        {
          step_id: "s3", phase: "recover", phase_label: "Recover", game_time: "9:40 AM",
          short: "The backup",
          situation: "The shared drive is locked. Dr. Rao wants to restore everything from the backup drive plugged into the server.",
          devices: { reception: "isolated", "file-server": "encrypted" },
          options: {
            staff: [
              { option_id: "a", text: "Leave the backup drive alone and tell the owner", actions: ["NOTIFY_OWNER"], correct: true, feedback: "Restoring is the owner's call, and the backup needs testing first." },
              { option_id: "b", text: "Plug the backup drive into the reception computer and copy files back", actions: [], correct: false, feedback: "The reception computer may still be infected. It could lock the backup too." }
            ],
            owner: [
              { option_id: "a", text: "Restore everything right away", actions: [], correct: false, feedback: "If the backup is old or damaged, you restore the problem. Test it first." },
              { option_id: "b", text: "Test the backup first, then restore onto a cleaned computer", actions: ["VERIFY_BACKUP"], correct: true, feedback: "Run the restore check before trusting the backup.", triggers: "restore_check" },
              { option_id: "c", text: "Reinstall Windows and skip the backup", actions: [], correct: false, feedback: "You'd lose every file since the computer was set up. Test the backup first." }
            ]
          }
        },
        {
          step_id: "s4", phase: "report", phase_label: "Report it", game_time: "11:30 AM",
          short: "Patient records",
          situation: "Patient records were on the locked drive.",
          devices: { reception: "isolated", "file-server": "encrypted" },
          options: {
            staff: [
              { option_id: "a", text: "Write down what you saw and when, and give it to the owner", actions: ["PRESERVE_EVIDENCE"], correct: true, feedback: "Your notes become the incident timeline." },
              { option_id: "b", text: "Delete the ransom note so patients don't see it", actions: [], correct: false, feedback: "That destroys evidence. Leave it and write down what you saw." }
            ],
            owner: [
              { option_id: "a", text: "Wait until everything is fixed", actions: [], correct: false, feedback: "CERT-In expects a report within 6 hours of noticing the incident." },
              { option_id: "b", text: "Report to CERT-In within 6 hours; start the patient-data breach record", actions: ["REPORT_CERTIN", "START_DPDP_NOTE"], correct: true, feedback: "Report now; the breach record covers the patient data." },
              { option_id: "c", text: "Don't report: nothing left the building", actions: [], correct: false, feedback: "Losing access to patient records counts as a personal-data breach, even if nothing was copied out." }
            ]
          }
        }
      ]
    }
  };

  const RESTORE_FIXTURE = {
    simulated: true,
    backup_age_hours: 216,
    limit_hours: 24,
    files_total: 50,
    files_ok: 48,
    failed_files: ["invoices/2026-09-billing.xlsx", "letters/referral-0412.docx"],
    exposed: true,
    duration_seconds: 3,
    fixes: [
      "Set the backup to run every night.",
      "Keep one copy unplugged: rotate two drives, one always off-site.",
      "Test again after the next backup."
    ]
  };

  window.SM_DATA = { SEED, DEVICE_STATUS, ACTIONS, LESSONS, UI_TEXT, SCENARIOS, RESTORE_FIXTURE };
})();
