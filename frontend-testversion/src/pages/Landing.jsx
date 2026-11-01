// Landing: a "Sunrise Clinic Security" brand card for 3 seconds, then the screen it wraps (the
// roles screen). Shown once per page load, so "Switch person" goes straight to the roles.
// Addresses like /staff/2 skip it, so a phone that already knows its person isn't held up.
import { useEffect, useState } from "react";
import { Shield } from "../components/Icons.jsx";

const SHOW_MS = 3000;
let shown = false;

export default function Landing({ children }) {
  const [done, setDone] = useState(shown);
  useEffect(() => {
    if (done) return undefined;
    const t = setTimeout(() => {
      shown = true;
      setDone(true);
    }, SHOW_MS);
    return () => clearTimeout(t);
  }, [done]);

  if (done) return children;
  return (
    <main className="landing">
      <div className="landing-inner">
        <span className="brand-row"><Shield style={{ width: 24, height: 24 }} /><span>ShieldMate</span></span>
        <h1>Sunrise Clinic Security</h1>
        <p>Security alerts, drills and backup checks for the clinic team.</p>
        <div className="landing-bar" role="progressbar" aria-label="Loading"><i /></div>
      </div>
    </main>
  );
}
