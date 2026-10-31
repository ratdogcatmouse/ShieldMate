(function () {
  "use strict";
  const U = window.SM_UI;
  ["i1", "i2", "i3", "i4"].forEach(id => { document.getElementById(id).innerHTML = U.ICONS.chevron; });
  document.getElementById("addr").textContent = location.protocol === "file:" ? "Serve this folder first (see README)" : location.origin + location.pathname.replace(/index\.html$/, "");
  document.getElementById("mode-pill").textContent = window.SM_CONFIG.mode === "mock" ? "Demo data" : "Live server";
  if (window.SM_CONFIG.judgeDrill) document.getElementById("judge-links").hidden = false;
  document.getElementById("mode").innerHTML = U.modeBanner();
})();
