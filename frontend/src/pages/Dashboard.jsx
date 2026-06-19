import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { leads as leadsApi, leaks as leaksApi } from "../services/api";
import useFetch from "../hooks/useFetch";
import {
  StatCardSkeleton,
  ErrorState,
  EmptyState,
  SeverityBadge,
} from "../components/ui";
import { formatRelative, titleCase } from "../utils/format";
import {
  IconDollar,
  IconInbox,
  IconOpportunities,
  IconLeak,
  IconArrowRight,
} from "../components/icons";

const STAT_META = [
  {
    key: "converted",
    label: "Revenue recovered",
    Icon: IconDollar,
    hint: "Leads marked converted",
  },
  {
    key: "manual_reviews",
    label: "Leads ignored",
    Icon: IconInbox,
    hint: "Awaiting human review",
  },
  {
    key: "hot_leads",
    label: "Hot opportunities",
    Icon: IconOpportunities,
    hint: "High-intent leads",
  },
  {
    key: "open_alerts",
    label: "Open leak alerts",
    Icon: IconLeak,
    hint: "Revenue at risk",
  },
];

export default function Dashboard() {
  const navigate = useNavigate();

  const load = useCallback(
    () => Promise.all([leadsApi.summary(), leaksApi.alerts()]),
    []
  );
  const { data, loading, error, refetch } = useFetch(load, []);

  const summary = data?.[0] || {};
  const alerts = data?.[1] || [];
  const openAlerts = alerts.filter(
    (a) => String(a.status).toLowerCase() === "open"
  );

  const values = {
    converted: summary.converted ?? 0,
    manual_reviews: summary.manual_reviews ?? 0,
    hot_leads: summary.hot_leads ?? 0,
    open_alerts: openAlerts.length,
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p className="sub">
            Where revenue is leaking and what to recover first.
          </p>
        </div>
      </div>

      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : (
        <>
          <div className="stat-grid">
            {loading
              ? Array.from({ length: 4 }).map((_, i) => (
                  <StatCardSkeleton key={i} />
                ))
              : STAT_META.map(({ key, label, Icon, hint }) => (
                  <div className="stat-card" key={key}>
                    <div className="stat-top">
                      <span className="stat-label">{label}</span>
                      <span className="stat-icon">
                        <Icon size={16} />
                      </span>
                    </div>
                    <div className="stat-value">{values[key]}</div>
                    <div className="stat-hint">{hint}</div>
                  </div>
                ))}
          </div>

          <div className="panel">
            <div className="spread panel-pad" style={{ paddingBottom: 0 }}>
              <div>
                <h2 style={{ fontSize: 15 }}>Recent leak alerts</h2>
                <p className="faint" style={{ fontSize: 12.5, marginTop: 2 }}>
                  Signals where deals are stalling.
                </p>
              </div>
              <button
                className="btn btn-sm"
                onClick={() => navigate("/leak-alerts")}
              >
                View all
                <IconArrowRight size={14} />
              </button>
            </div>

            <div className="divider" style={{ margin: "14px 0 0" }} />

            {loading ? (
              <div className="panel-pad">
                <RowsSkeleton />
              </div>
            ) : openAlerts.length === 0 ? (
              <EmptyState
                title="No open alerts"
                message="Nothing is leaking right now. Run a scan to check again."
              />
            ) : (
              openAlerts.slice(0, 5).map((a) => (
                <div className="alert-row" key={a.id}>
                  <div
                    className="alert-icon"
                    style={{
                      background: "var(--red-soft)",
                      color: "var(--red)",
                    }}
                  >
                    <IconLeak size={18} />
                  </div>
                  <div className="alert-main">
                    <div className="alert-title">{titleCase(a.leak_type)}</div>
                    <div className="alert-detail">
                      {a.detail ||
                        `${titleCase(a.entity_type)} #${a.entity_id}`}
                    </div>
                  </div>
                  <SeverityBadge value={a.severity} />
                  <span className="alert-time">
                    {formatRelative(a.detected_at)}
                  </span>
                </div>
              ))
            )}
          </div>
        </>
      )}
    </>
  );
}

function RowsSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="row" style={{ gap: 14 }}>
          <span
            className="skel"
            style={{ width: 36, height: 36, borderRadius: 9 }}
          />
          <span className="skel" style={{ flex: 1, height: 14 }} />
          <span
            className="skel"
            style={{ width: 60, height: 20, borderRadius: 100 }}
          />
        </div>
      ))}
    </div>
  );
}
