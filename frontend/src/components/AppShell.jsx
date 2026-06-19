import { useEffect, useState } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { NAV_ITEMS } from "./nav";
import CommandPalette from "./CommandPalette";
import { tokenStore } from "../services/api";
import {
  IconPulse,
  IconSearch,
  IconLogout,
  IconMenu,
  IconClose,
} from "./icons";

const PAGE_TITLES = {
  "/dashboard": "Dashboard",
  "/leads": "Leads",
  "/opportunities": "Opportunities",
  "/leak-alerts": "Leak Alerts",
  "/sequences": "Sequences",
};

/**
 * Dark-mode application shell: fixed sidebar, top bar, content outlet.
 * Owns the command palette and the global Cmd/Ctrl+K shortcut.
 */
export default function AppShell({ children }) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  // Global Cmd/Ctrl+K toggle.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setMobileNav(false);
  }, [location.pathname]);

  const logout = () => {
    tokenStore.clear();
    navigate("/login");
  };

  const title = PAGE_TITLES[location.pathname] || "LeadPulse";

  return (
    <div className="shell">
      <div
        className={`backdrop ${mobileNav ? "show" : ""}`}
        onClick={() => setMobileNav(false)}
        aria-hidden="true"
      />

      <aside className={`sidebar ${mobileNav ? "open" : ""}`}>
        <div className="sidebar-brand">
          <span className="brand-mark" aria-hidden="true">
            <IconPulse size={18} />
          </span>
          <div>
            <div className="brand-name">LeadPulse</div>
            <div className="brand-sub">Revenue Recovery</div>
          </div>
        </div>

        <nav className="nav" aria-label="Primary">
          <span className="nav-label">Workspace</span>
          {NAV_ITEMS.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `nav-item ${isActive ? "active" : ""}`
              }
            >
              <Icon size={17} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button className="btn btn-ghost" onClick={logout} style={{ width: "100%" }}>
            <IconLogout size={16} />
            Sign out
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="row">
            <button
              className="icon-btn menu-btn"
              aria-label="Open navigation menu"
              onClick={() => setMobileNav(true)}
            >
              {mobileNav ? <IconClose size={18} /> : <IconMenu size={18} />}
            </button>
            <span className="topbar-title">{title}</span>
          </div>

          <div className="topbar-actions">
            <button
              className="cmdk-trigger"
              onClick={() => setPaletteOpen(true)}
              aria-label="Open command palette"
            >
              <IconSearch size={15} />
              <span className="cmdk-trigger-label">Search</span>
              <span className="kbd">⌘K</span>
            </button>
          </div>
        </header>

        <main className="content">
          <div className="content-inner">{children}</div>
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
