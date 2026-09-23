/**
 * Copies the widget into the dashboard's public folder before the app
 * starts.
 *
 * Why this exists: the widget must be reachable over HTTP for testing
 * (http://localhost:3000/demo.html) and for any site that loads it from
 * this deployment. Next.js only serves files inside public/. Keeping a
 * second hand-maintained copy there is how the two drift apart — you edit
 * one, the browser shows the other, and nothing you change appears.
 *
 * So widget/ stays the single source of truth and public/ is generated.
 * The copies are gitignored for the same reason.
 *
 * Runs automatically via the "predev" and "prebuild" scripts.
 */
const fs = require("fs");
const path = require("path");

const source = path.join(__dirname, "..", "..", "widget");
const target = path.join(__dirname, "..", "public");
const files = ["oasis-chatbot-widget.js", "demo.html"];

if (!fs.existsSync(source)) {
  // The dashboard can be deployed on its own (Vercel, say) with no widget
  // folder alongside it. That is a valid setup, not a failure.
  console.log("[widget] no widget/ folder next to the dashboard — skipping copy");
  process.exit(0);
}

fs.mkdirSync(target, { recursive: true });

let copied = 0;
for (const file of files) {
  const from = path.join(source, file);
  if (!fs.existsSync(from)) continue;
  fs.copyFileSync(from, path.join(target, file));
  copied += 1;
}

console.log(`[widget] copied ${copied} file(s) from widget/ into public/`);
