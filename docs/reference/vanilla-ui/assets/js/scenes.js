/* Scene pictures for the game-style drill: one per moment, plain SVG (no images). */
(function () {
  "use strict";
  const DESK = '<rect x="0" y="170" width="390" height="60" fill="#14173A"/><rect x="40" y="150" width="310" height="22" rx="6" fill="#3A3F7A"/>' +
    '<rect x="60" y="172" width="16" height="58" fill="#2C3166"/><rect x="314" y="172" width="16" height="58" fill="#2C3166"/>';
  const SPARK = '<circle cx="70" cy="60" r="5" fill="#F5A524"/><circle cx="95" cy="40" r="3" fill="#F5A524" opacity=".6"/><circle cx="345" cy="38" r="4" fill="#F5A524" opacity=".7"/>';
  const open = (label) => '<svg class="scene" viewBox="0 0 390 230" role="img" aria-label="' + label + '">';

  window.SM_SCENES = {
    s1: open("The reception computer shows a padlock and a ransom note") + DESK + SPARK +
      '<rect x="120" y="40" width="150" height="100" rx="10" fill="#0B0E26" stroke="#5B61B5" stroke-width="3"/>' +
      '<rect class="blink" x="128" y="48" width="134" height="84" rx="6" fill="#4A0F14"/>' +
      '<rect x="178" y="78" width="34" height="28" rx="4" fill="none" stroke="#FFB4B4" stroke-width="4"/><path d="M184 78v-8a11 11 0 0 1 22 0v8" fill="none" stroke="#FFB4B4" stroke-width="4"/>' +
      '<rect x="186" y="140" width="18" height="12" fill="#3A3F7A"/>' +
      '<g transform="rotate(8 303 111)"><rect x="276" y="78" width="54" height="66" rx="4" fill="#FFF6D6"/><path d="M286 96h30M286 106h26M286 116h30M286 126h18" stroke="#B25C00" stroke-width="3"/></g>' +
      '<text x="302" y="68" text-anchor="middle" fill="#F5A524" font-size="13" font-weight="700" font-family="sans-serif">RANSOM NOTE</text></svg>',

    s2: open("A ransom note with a fake IT support phone number and a payment link") + DESK + SPARK +
      '<rect x="95" y="28" width="200" height="118" rx="8" fill="#FFF6D6"/>' +
      '<text x="195" y="56" text-anchor="middle" fill="#7A3306" font-size="15" font-weight="700" font-family="sans-serif">YOUR FILES ARE LOCKED</text>' +
      '<rect x="118" y="70" width="154" height="26" rx="6" fill="#FFE1B3"/><text x="195" y="88" text-anchor="middle" fill="#7A3306" font-size="13" font-family="monospace">IT SUPPORT: +00 000 000</text>' +
      '<rect x="138" y="106" width="114" height="26" rx="13" fill="#B42318"/><text x="195" y="124" text-anchor="middle" fill="#FFFFFF" font-size="13" font-weight="700" font-family="sans-serif">PAY NOW</text>' +
      '<g transform="translate(300 96)"><rect x="0" y="0" width="40" height="66" rx="8" fill="#0B0E26" stroke="#5B61B5" stroke-width="3"/><circle cx="20" cy="56" r="3" fill="#5B61B5"/><path d="M12 22h16M12 30h16" stroke="#F5A524" stroke-width="3"/></g>' +
      '<text x="320" y="88" text-anchor="middle" fill="#F5A524" font-size="20" font-weight="700" font-family="sans-serif">?</text></svg>',

    s3: open("The file server with a backup drive plugged in all the time") + SPARK +
      '<rect x="0" y="190" width="390" height="40" fill="#14173A"/>' +
      '<rect x="120" y="30" width="90" height="160" rx="8" fill="#0B0E26" stroke="#5B61B5" stroke-width="3"/>' +
      '<path d="M134 60h62M134 84h62M134 108h62" stroke="#3A3F7A" stroke-width="6"/><circle cx="190" cy="150" r="5" fill="#F04438" class="blink"/>' +
      '<path d="M210 130 C 240 130, 240 160, 262 160" fill="none" stroke="#C7CAF2" stroke-width="4"/>' +
      '<rect x="262" y="140" width="66" height="46" rx="8" fill="#2C3166" stroke="#C7CAF2" stroke-width="3"/>' +
      '<text x="295" y="168" text-anchor="middle" fill="#FFFFFF" font-size="13" font-weight="700" font-family="sans-serif">BACKUP</text>' +
      '<text x="295" y="128" text-anchor="middle" fill="#F5A524" font-size="26" font-weight="700" font-family="sans-serif">?</text></svg>',

    s4: open("A folder of patient records with a padlock, and a clock at 11:30") + DESK + SPARK +
      '<path d="M110 60h60l12 14h96v76H110z" fill="#F5C66B"/><rect x="110" y="82" width="168" height="68" rx="4" fill="#FFD98A"/>' +
      '<text x="194" y="122" text-anchor="middle" fill="#7A3306" font-size="15" font-weight="700" font-family="sans-serif">PATIENT RECORDS</text>' +
      '<rect x="176" y="128" width="36" height="28" rx="4" fill="#B42318"/><path d="M182 128v-8a12 12 0 0 1 24 0v8" fill="none" stroke="#B42318" stroke-width="4"/>' +
      '<circle cx="320" cy="62" r="28" fill="#0B0E26" stroke="#5B61B5" stroke-width="3"/><path d="M320 62V84M320 62L315 46" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round"/>' +
      '<text x="320" y="112" text-anchor="middle" fill="#C7CAF2" font-size="13" font-family="sans-serif">11:30 AM</text></svg>'
  };
})();
