import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  Outlet,
} from "react-router-dom";

import { tokenStore } from "./services/api";
import AppShell from "./components/AppShell";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Leads from "./pages/Leads";
import Opportunities from "./pages/Opportunities";
import LeakAlerts from "./pages/LeakAlerts";
import Sequences from "./pages/Sequences";

/**
 * Guards authenticated routes and wraps them in the app shell.
 * Unauthenticated users are redirected to /login.
 */
function ProtectedLayout() {
  if (!tokenStore.isAuthed()) {
    return <Navigate to="/login" replace />;
  }
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route element={<ProtectedLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/leads" element={<Leads />} />
          <Route path="/opportunities" element={<Opportunities />} />
          <Route path="/leak-alerts" element={<LeakAlerts />} />
          <Route path="/sequences" element={<Sequences />} />
        </Route>

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
