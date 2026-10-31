// Export assets/js/data.js (the single source of scenario/lesson data) to backend/shieldmate_data.json.
// Run after editing data.js:  node tools/export-data.js
const fs = require("fs"), path = require("path");
global.window = {};
require(path.join(__dirname, "..", "assets", "js", "data.js"));
const out = path.join(__dirname, "..", "backend", "shieldmate_data.json");
fs.writeFileSync(out, JSON.stringify(global.window.SM_DATA, null, 1));
console.log("wrote", out);
