import { Route, Routes } from "react-router-dom";
import { OwnerShell, PhoneShell } from "./components/Shells.jsx";
import Start from "./routes/Start.jsx";
import Staff from "./routes/Staff.jsx";
import Owner from "./routes/Owner.jsx";
import Drill from "./routes/Drill.jsx";
import Backstage from "./routes/Backstage.jsx";

export default function App() {
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
