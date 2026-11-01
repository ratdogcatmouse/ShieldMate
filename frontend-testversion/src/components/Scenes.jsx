// Scene pictures for the drill: one per step of "Ransomware at the clinic".
// Plain SVG, no images: flat line drawings in the slate palette, shown on a light panel.

const DESK = (
  <>
    <rect x="40" y="150" width="310" height="14" rx="3" fill="#C9D2DD"/><rect x="60" y="164" width="12" height="66" fill="#DCE2EA"/><rect x="318" y="164" width="12" height="66" fill="#DCE2EA"/>
  </>
);

function Scene({ label, children }) {
  return (
    <div className="scene-panel">
      <svg className="scene" viewBox="0 0 390 230" role="img" aria-label={label}>
        {children}
      </svg>
    </div>
  );
}

const SCENES = {
  ransomware_clinic: {
    s1: (
      <Scene label="The reception computer shows a padlock and a ransom note">
        {DESK}<rect x="120" y="40" width="150" height="100" rx="10" fill="#FFFFFF" stroke="#2E3B4C" strokeWidth="3"/><rect x="128" y="48" width="134" height="84" rx="6" fill="#FDEEEC"/><rect x="178" y="78" width="34" height="28" rx="4" fill="none" stroke="#B42318" strokeWidth="4"/><path d="M184 78v-8a11 11 0 0 1 22 0v8" fill="none" stroke="#B42318" strokeWidth="4"/><rect x="186" y="140" width="18" height="12" fill="#2E3B4C"/><g transform="rotate(8 303 111)"><rect x="276" y="78" width="54" height="66" rx="4" fill="#FFFFFF" stroke="#2E3B4C" strokeWidth="2"/><path d="M286 96h30M286 106h26M286 116h30M286 126h18" stroke="#8593A5" strokeWidth="3"/></g><text x="302" y="68" textAnchor="middle" fill="#2E3B4C" fontSize="13" fontWeight="700" fontFamily="sans-serif">RANSOM NOTE</text>
      </Scene>
    ),
    s2: (
      <Scene label="A ransom note with a fake IT support phone number and a payment link">
        {DESK}<rect x="95" y="28" width="200" height="118" rx="8" fill="#FFFFFF" stroke="#2E3B4C" strokeWidth="2"/><text x="195" y="56" textAnchor="middle" fill="#2E3B4C" fontSize="15" fontWeight="700" fontFamily="sans-serif">YOUR FILES ARE LOCKED</text><rect x="118" y="70" width="154" height="26" rx="6" fill="#EEF1F5"/><text x="195" y="88" textAnchor="middle" fill="#2E3B4C" fontSize="13" fontFamily="monospace">IT SUPPORT: +00 000 000</text><rect x="138" y="106" width="114" height="26" rx="13" fill="#B42318"/><text x="195" y="124" textAnchor="middle" fill="#FFFFFF" fontSize="13" fontWeight="700" fontFamily="sans-serif">PAY NOW</text><g transform="translate(300 96)"><rect x="0" y="0" width="40" height="66" rx="8" fill="#FFFFFF" stroke="#2E3B4C" strokeWidth="3"/><circle cx="20" cy="56" r="3" fill="#2E3B4C"/><path d="M12 22h16M12 30h16" stroke="#8593A5" strokeWidth="3"/></g><text x="320" y="88" textAnchor="middle" fill="#2E3B4C" fontSize="20" fontWeight="700" fontFamily="sans-serif">?</text>
      </Scene>
    ),
    s3: (
      <Scene label="The file server with a backup drive plugged in all the time">
        <rect x="20" y="190" width="350" height="8" rx="3" fill="#C9D2DD"/><rect x="120" y="30" width="90" height="160" rx="8" fill="#FFFFFF" stroke="#2E3B4C" strokeWidth="3"/><path d="M134 60h62M134 84h62M134 108h62" stroke="#C9D2DD" strokeWidth="6"/><circle cx="190" cy="150" r="5" fill="#F04438"/><path d="M210 130 C 240 130, 240 160, 262 160" fill="none" stroke="#556274" strokeWidth="4"/><rect x="262" y="140" width="66" height="46" rx="8" fill="#FFFFFF" stroke="#556274" strokeWidth="3"/><text x="295" y="168" textAnchor="middle" fill="#2E3B4C" fontSize="13" fontWeight="700" fontFamily="sans-serif">BACKUP</text><text x="295" y="128" textAnchor="middle" fill="#2E3B4C" fontSize="26" fontWeight="700" fontFamily="sans-serif">?</text>
      </Scene>
    ),
    s4: (
      <Scene label="A folder of patient records with a padlock, and a clock at 11:30">
        {DESK}<path d="M110 60h60l12 14h96v76H110z" fill="#C9D2DD"/><rect x="110" y="82" width="168" height="68" rx="4" fill="#E6EAF0"/><text x="194" y="122" textAnchor="middle" fill="#2E3B4C" fontSize="15" fontWeight="700" fontFamily="sans-serif">PATIENT RECORDS</text><rect x="176" y="128" width="36" height="28" rx="4" fill="#B42318"/><path d="M182 128v-8a12 12 0 0 1 24 0v8" fill="none" stroke="#B42318" strokeWidth="4"/><circle cx="320" cy="62" r="28" fill="#FFFFFF" stroke="#2E3B4C" strokeWidth="3"/><path d="M320 62V84M320 62L315 46" stroke="#2E3B4C" strokeWidth="3" strokeLinecap="round"/><text x="320" y="112" textAnchor="middle" fill="#556274" fontSize="13" fontFamily="sans-serif">11:30 AM</text>
      </Scene>
    ),
  },
};

// The picture for a drill step, or null when the scenario has none.
export function sceneFor(scenarioId, stepId) {
  return SCENES[scenarioId]?.[stepId] ?? null;
}
