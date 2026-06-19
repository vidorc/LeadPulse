import { useCallback, useState } from "react";
import { leaks as leaksApi, errorMessage } from "../services/api";
import useFetch from "../hooks/useFetch";
import {
  ErrorState,
  EmptyState,
  Skeleton,
  SeverityBadge,
  StatusBadge,
} from "../components/ui";
import { formatRelative, titleCase } from "../utils/format";
import { IconLeak, IconRefresh, IconCheck } from "../components/icons";

export default function LeakAlerts() {
  const { data, loading, error, refetch } = useFetch(leaksApi.alerts, []);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState("");

  const alerts = data || [];
  const open = alerts.filter((a) => String(a.status).toLowerCase() === "open");

  const runScan = useCallback(async () => {
    setScanning(true);
    setScanError("");
    try {
      await leaksApi.scan();
      await refetch();
    } catch (err) {
      setScanError(errorMessage(err, "Scan failed."));
    } finally {
      setScanning(false);
    }
  }, [refetch]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Leak Alerts</h1>
          <p className="sub">
            SLA breaches where revenue is slipping through the cracks.
          </p>
        </div>
        <button className="btn btn-primary" onClick={runScan} disabled={scanning}>
          <IconRefresh size={15} className={scanning ? "spin" : ""} />
          {scanning ? "Scanning…" : "Run scan"}
        </button>
      </div>

      {scanError && (
        <div className="auth-error" role="alert" style={{ marginBottom: 16 }}>
          {scanError}
        </div>
      )}

      {!loading && !error && alerts.length > 0 && (
        <div className="row" style={{ marginBottom: 16, gap: 8 }}>
          <span className="badge badge-red">{open.length} open</span>
          <span className="badge badge-neutral">
            {alerts.length - open.length} resolved
          </span>
        </div>
      )}

      <div className="panel">
        {error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : loading ? (
          <div className="panel-pad" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {Array.from({ length: 5 }).map((_, i) => (
              <div className="row" key={i} style={{ gap: 14 }}>
                <span className="skel" style={{ width: 36, height: 36, borderRadius: 9 }} />
                <Skeleton style={{ flex: 1 }} />
                <span className="skel" style={{ width: 64, height: 20, borderRadius: 100 }} />
              </div>
            ))}
          </div>
        ) : alerts.length === 0 ? (
          <EmptyState
            icon={<IconCheck size={22} />}
            title="No leaks detected"
            message="Everything is within SLA. Run a scan to check for new breaches."
            action={
              <button className="btn" onClick={runScan} disabled={scanning}>
                <IconRefresh size={15} className={scanning ? "spin" : ""} />
                Run scan
              </button>
            }
          />
        ) : (
          alerts.map((a) => {
            const isOpen = String(a.status).toLowerCase() === "open";
            return (
              <div className="alert-row" key={a.id}>
                <div
                  className="alert-icon"
                  style={{
                    background: isOpen ? "var(--red-soft)" : "var(--panel-hover)",
                    color: isOpen ? "var(--red)" : "var(--text-faint)",
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
                <StatusBadge value={a.status} />
                <span className="alert-time">
                  {formatRelative(a.detected_at)}
                </span>
              </div>
            );
          })
        )}
      </div>
    </>
  );
}
