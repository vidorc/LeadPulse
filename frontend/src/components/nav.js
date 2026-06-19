import {
  IconDashboard,
  IconLeads,
  IconOpportunities,
  IconLeak,
  IconSequence,
} from "./icons";

/**
 * Single source of truth for primary navigation.
 * Consumed by the sidebar and the command palette.
 */
export const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", Icon: IconDashboard },
  { to: "/leads", label: "Leads", Icon: IconLeads },
  { to: "/opportunities", label: "Opportunities", Icon: IconOpportunities },
  { to: "/leak-alerts", label: "Leak Alerts", Icon: IconLeak },
  { to: "/sequences", label: "Sequences", Icon: IconSequence },
];
