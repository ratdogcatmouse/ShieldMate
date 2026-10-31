import { useEffect, useRef } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { OwnerShell, PhoneShell } from "./components/Shells.jsx";
import Start from "./routes/Start.jsx";
import Staff from "./routes/Staff.jsx";
import Owner from "./routes/Owner.jsx";
import Drill from "./routes/Drill.jsx";
import Backstage from "./routes/Backstage.jsx";
import { track } from "./telemetry.js";

// One ui.page_view per screen, here rather than in a shell because /backstage has none.
// The ref skips StrictMode's second run of the effect in development.
function usePageViews() {
  const { pathname } = useLocation();
  const last = useRef(null);
  useEffect(() => {
    if (last.current === pathname) return;
    last.current = pathname;
    track("ui.page_view");
  }, [pathname]);
}

export default function App() {
  usePageViews();
  return (
    <Routes>
      <Route element={<PhoneShell />}>
        <Route path="/" element={<Start />} />
        <Route path="/staff/:staffId" element={<Staff />} />
        <Route path="/drill/:code" element={<Drill />} />
        <Route path="*" element={<Start />} />
      </Route>
      <Route element={<OwnerShell />}>
        <Route path="/owner" element={<Owner />} />
      </Route>
      <Route path="/backstage" element={<Backstage />} />
    </Routes>
  );
}
