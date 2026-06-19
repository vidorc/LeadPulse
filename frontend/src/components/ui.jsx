import { IconInbox, IconRefresh, IconLeak } from "./icons";
import { titleCase } from "../utils/format";

/* --------------------------------- badges --------------------------------- */
const SEVERITY_TONE = { high: "red", medium: "amber", low: "blue" };
const STATUS_TONE = {
  open: "amber",
  resolved: "green",
  dismissed: "neutral",
  new: "blue",
  converted: "green",
  lost: "red",
  won: "green",
  qualified: "accent",
};

export function Badge({ tone = "neutral", dot = false, children }) {
  return (
    <span className={`badge badge-${tone}`}>
      {dot && <span className="dot" />}
      {children}
    </span>
  );
}

export function SeverityBadge({ value }) {
  const tone = SEVERITY_TONE[String(value).toLowerCase()] || "neutral";
  return (
    <Badge tone={tone} dot>
      {titleCase(value)}
    </Badge>
  );
}

export function StatusBadge({ value }) {
  const tone = STATUS_TONE[String(value).toLowerCase()] || "neutral";
  return <Badge tone={tone}>{titleCase(value)}</Badge>;
}

/* ------------------------------- skeletons -------------------------------- */
export function Skeleton({ width = "100%", height = 14, radius = 6, style }) {
  return (
    <span
      className="skel"
      style={{
        display: "block",
        width,
        height,
        borderRadius: radius,
        ...style,
      }}
    />
  );
}

export function StatCardSkeleton() {
  return (
    <div className="stat-card">
      <div className="stat-top">
        <Skeleton width={90} height={12} />
        <Skeleton width={30} height={30} radius={8} />
      </div>
      <Skeleton width={70} height={30} />
    </div>
  );
}

export function RowSkeleton({ cols = 4 }) {
  return (
    <tr>
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i}>
          <Skeleton width={i === 0 ? "60%" : "40%"} />
        </td>
      ))}
    </tr>
  );
}

/* ----------------------------- empty / error ------------------------------ */
export function EmptyState({
  icon = <IconInbox size={22} />,
  title = "Nothing here yet",
  message = "",
  action = null,
}) {
  return (
    <div className="state">
      <div className="state-icon">{icon}</div>
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message = "Failed to load.", onRetry }) {
  return (
    <div className="state error">
      <div className="state-icon">
        <IconLeak size={22} />
      </div>
      <h3>Something went wrong</h3>
      <p>{message}</p>
      {onRetry && (
        <button className="btn" onClick={onRetry}>
          <IconRefresh size={15} />
          Try again
        </button>
      )}
    </div>
  );
}
