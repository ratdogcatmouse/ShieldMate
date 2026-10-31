/* Look and feel. Loaded in <head> so the page never flashes the wrong theme.
   "bold": violet signature brand (the upgrade). "calm": the original clinic blue.
   Override for one tab with ?theme=calm or ?theme=bold. */
(function () {
  var DEFAULT_THEME = "bold";
  var t = DEFAULT_THEME;
  try {
    var q = new URLSearchParams(location.search).get("theme");
    if (q === "bold" || q === "calm") sessionStorage.setItem("sm-theme", q);
    t = sessionStorage.getItem("sm-theme") || DEFAULT_THEME;
  } catch (e) { /* storage blocked: default */ }
  document.documentElement.setAttribute("data-theme", t);
})();
