import { useState } from "react";
import {
  opportunities as oppApi,
  errorMessage,
} from "../services/api";
import useFetch from "../hooks/useFetch";
import {
  ErrorState,
  EmptyState,
  Skeleton,
} from "../components/ui";
import { formatCurrency, formatRelative, titleCase } from "../utils/format";
import {
  IconPlus,
  IconClose,
  IconOpportunities,
  IconArrowRight,
} from "../components/icons";

const STAGES = [
  "new",
  "contacted",
  "qualified",
  "proposal_sent",
  "negotiation",
  "won",
  "lost",
];

// Stage -> the stage it advances to. Terminal stages have no "next".
const NEXT_STAGE = {
  new: "contacted",
  contacted: "qualified",
  qualified: "proposal_sent",
  proposal_sent: "negotiation",
  negotiation: "won",
};

export default function Opportunities() {
  const { data, loading, error, refetch, setData } = useFetch(
    oppApi.list,
    []
  );
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: "", value_amount: "" });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [advancing, setAdvancing] = useState(null);

  const opps = data || [];

  const grouped = STAGES.reduce((acc, stage) => {
    acc[stage] = opps.filter((o) => o.stage === stage);
    return acc;
  }, {});

  const advance = async (opp) => {
    const next = NEXT_STAGE[opp.stage];
    if (!next) return;
    setAdvancing(opp.id);
    try {
      const updated = await oppApi.setStage(opp.id, next);
      setData(opps.map((o) => (o.id === opp.id ? updated : o)));
    } catch (err) {
      // Surface failures inline rather than silently swallowing.
      alert(errorMessage(err, "Could not advance stage."));
    } finally {
      setAdvancing(null);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    setFormError("");
    setSubmitting(true);
    try {
      const created = await oppApi.create({
        title: form.title,
        value_amount: form.value_amount
          ? Number(form.value_amount)
          : undefined,
      });
      setData([created, ...opps]);
      setForm({ title: "", value_amount: "" });
      setShowForm(false);
    } catch (err) {
      setFormError(errorMessage(err, "Could not create opportunity."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Opportunities</h1>
          <p className="sub">Move deals forward before they go cold.</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setShowForm((s) => !s)}
        >
          {showForm ? <IconClose size={16} /> : <IconPlus size={16} />}
          {showForm ? "Cancel" : "New opportunity"}
        </button>
      </div>

      {showForm && (
        <form
          className="panel panel-pad"
          onSubmit={submit}
          style={{ marginBottom: 20 }}
        >
          {formError && (
            <div className="auth-error" role="alert" style={{ marginBottom: 14 }}>
              {formError}
            </div>
          )}
          <div className="grid-2">
            <div className="field">
              <label htmlFor="o-title">Title</label>
              <input
                id="o-title"
                className="input"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="Acme — annual contract"
                required
              />
            </div>
            <div className="field">
              <label htmlFor="o-value">Value (USD)</label>
              <input
                id="o-value"
                type="number"
                min="0"
                className="input"
                value={form.value_amount}
                onChange={(e) =>
                  setForm({ ...form, value_amount: e.target.value })
                }
                placeholder="25000"
              />
            </div>
          </div>
          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? "Saving…" : "Create opportunity"}
          </button>
        </form>
      )}

      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : !loading && opps.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={<IconOpportunities size={22} />}
            title="No opportunities yet"
            message="Create one to start tracking it through your pipeline."
            action={
              <button className="btn" onClick={() => setShowForm(true)}>
                <IconPlus size={15} />
                New opportunity
              </button>
            }
          />
        </div>
      ) : (
        <div className="kanban">
          {STAGES.map((stage) => (
            <section className="kanban-col" key={stage} aria-label={titleCase(stage)}>
              <div className="kanban-col-head">
                <span className="kanban-col-title">
                  {titleCase(stage)}
                </span>
                <span className="kanban-count">
                  {loading ? "·" : grouped[stage].length}
                </span>
              </div>
              <div className="kanban-body">
                {loading ? (
                  <>
                    <Skeleton height={64} radius={10} />
                    <Skeleton height={64} radius={10} />
                  </>
                ) : grouped[stage].length === 0 ? (
                  <span className="faint" style={{ fontSize: 12, padding: 4 }}>
                    Empty
                  </span>
                ) : (
                  grouped[stage].map((opp) => (
                    <article className="opp-card" key={opp.id}>
                      <div className="opp-title">{opp.title}</div>
                      <div className="opp-meta">
                        <span className="opp-value">
                          {formatCurrency(opp.value_amount, opp.currency)}
                        </span>
                        <span className="faint" style={{ fontSize: 11.5 }}>
                          {formatRelative(opp.stage_changed_at)}
                        </span>
                      </div>
                      {NEXT_STAGE[opp.stage] && (
                        <div className="opp-actions">
                          <button
                            className="btn btn-sm"
                            style={{ width: "100%" }}
                            disabled={advancing === opp.id}
                            onClick={() => advance(opp)}
                          >
                            {advancing === opp.id
                              ? "Advancing…"
                              : `Move to ${titleCase(NEXT_STAGE[opp.stage])}`}
                            <IconArrowRight size={13} />
                          </button>
                        </div>
                      )}
                    </article>
                  ))
                )}
              </div>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
