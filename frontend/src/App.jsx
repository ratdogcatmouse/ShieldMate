import { useEffect, useRef } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { ToastProvider } from "./components/ui.jsx";
import { getStatus } from "./lib/api.js";
import { track } from "./lib/telemetry.js";
import { syncServerTime } from "./lib/time.js";
import { usePoll } from "./lib/usePoll.js";
import Start from "./pages/Start.jsx";
import Staff from "./pages/Staff.jsx";
import StaffDrill from "./pages/StaffDrill.jsx";
import OwnerNow from "./pages/OwnerNow.jsx";
import OwnerReadiness from "./pages/OwnerReadiness.jsx";
import OwnerDrill from "./pages/OwnerDrill.jsx";
import OwnerNotify from "./pages/OwnerNotify.jsx";
import Mission from "./pages/Mission.jsx";
import ItPanel from "./pages/ItPanel.jsx";
import Backstage from "./pages/Backstage.jsx";

// One ui.page_view per screen. The ref skips StrictMode's second run of the effect in development.
function usePageViews() {
  const { pathname } = useLocation();
  const last = useRef(null);
  useEffect(() => {
    if (last.current === pathname) return;
    last.current = pathname;
    track("ui.page_view");
  }, [pathname]);
}

// Keeps countdowns on the server's clock (Backstage can skip it ahead).
function useServerClock() {
  const { data } = usePoll(getStatus, 10000);
  useEffect(() => {
    if (data) syncServerTime(data.server_time);
  }, [data]);
}

export default function App() {
  usePageViews();
  useServerClock();
  return (
    <ToastProvider>
      <Routes>
        <Route path="/" element={<Start />} />
        <Route path="/staff/:staffId" element={<Staff view="today" />} />
        <Route path="/staff/:staffId/history" element={<Staff view="history" />} />
        <Route path="/staff/:staffId/drill" element={<StaffDrill />} />
        <Route path="/owner" element={<OwnerNow />} />
        <Route path="/owner/readiness" element={<OwnerReadiness />} />
        <Route path="/owner/drill" element={<OwnerDrill />} />
        <Route path="/owner/notify" element={<OwnerNotify />} />
        <Route path="/mission" element={<Mission />} />
        <Route path="/it" element={<ItPanel />} />
        <Route path="/backstage" element={<Backstage />} />
        <Route path="*" element={<Start />} />
      </Routes>
    </ToastProvider>
  );
}
