import { useState } from "react";
import { sequences as seqApi, errorMessage } from "../services/api";
import useFetch from "../hooks/useFetch";
import {
  ErrorState,
  EmptyState,
  Skeleton,
  Badge,
} from "../components/ui";
import { IconPlus, IconClose, IconSequence } from "../components/icons";

const NEW_STEP = () => ({
  delay_hours: 24,
  action: "email",
  subject: "",
  body: "",
});

export default function Sequences() {
  const { data, loading, error, refetch, setData } = useFetch(
    seqApi.list,
    []
  );
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [steps, setSteps] = useState([NEW_STEP()]);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  const list = data || [];

  const updateStep = (i, key, value) =>
    setSteps(steps.map((s, idx) => (idx === i ? { ...s, [key]: value } : s)));

  const addStep = () => setSteps([...steps, NEW_STEP()]);
  const removeStep = (i) =>
    setSteps(steps.length > 1 ? steps.filter((_, idx) => idx !== i) : steps);

  const reset = () => {
    setName("");
    setSteps([NEW_STEP()]);
    setFormError("");
  };

  const submit = async (e) => {
    e.preventDefault();
    setFormError("");
    setSubmitting(true);
    try {
      const created = await seqApi.create({
        name,
        steps: steps.map((s) => ({
          delay_hours: Number(s.delay_hours) || 0,
          action: s.action || "email",
          subject: s.subject || undefined,
          body: s.body || undefined,
        })),
      });
      setData([created, ...list]);
      reset();
      setShowForm(false);
    } catch (err) {
      setFormError(errorMessage(err, "Could not create sequence."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Sequences</h1>
          <p className="sub">Automated follow-ups that keep deals warm.</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setShowForm((s) => !s)}
        >
          {showForm ? <IconClose size={16} /> : <IconPlus size={16} />}
          {showForm ? "Cancel" : "New sequence"}
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
          <div className="field">
            <label htmlFor="s-name">Sequence name</label>
            <input
              id="s-name"
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Post-demo nurture"
              required
            />
          </div>

          <div className="divider" />
          <div className="spread" style={{ marginBottom: 12 }}>
            <span className="muted" style={{ fontSize: 13, fontWeight: 500 }}>
              Steps
            </span>
            <button type="button" className="btn btn-sm" onClick={addStep}>
              <IconPlus size={14} />
              Add step
            </button>
          </div>

          {steps.map((step, i) => (
            <div
              key={i}
              className="panel panel-pad"
              style={{ background: "var(--inset)", marginBottom: 12 }}
            >
              <div className="spread" style={{ marginBottom: 12 }}>
                <Badge tone="accent">Step {i + 1}</Badge>
                {steps.length > 1 && (
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={`Remove step ${i + 1}`}
                    onClick={() => removeStep(i)}
                  >
                    <IconClose size={15} />
                  </button>
                )}
              </div>
              <div className="grid-2">
                <div className="field">
                  <label>Delay (hours)</label>
                  <input
                    type="number"
                    min="0"
                    className="input"
                    value={step.delay_hours}
                    onChange={(e) =>
                      updateStep(i, "delay_hours", e.target.value)
                    }
                  />
                </div>
                <div className="field">
                  <label>Action</label>
                  <select
                    className="input"
                    value={step.action}
                    onChange={(e) => updateStep(i, "action", e.target.value)}
                  >
                    <option value="email">Email</option>
                    <option value="sms">SMS</option>
                    <option value="task">Task</option>
                  </select>
                </div>
              </div>
              <div className="field">
                <label>Subject</label>
                <input
                  className="input"
                  value={step.subject}
                  onChange={(e) => updateStep(i, "subject", e.target.value)}
                  placeholder="Quick follow-up on your demo"
                />
              </div>
              <div className="field" style={{ marginBottom: 0 }}>
                <label>Body</label>
                <textarea
                  className="input"
                  value={step.body}
                  onChange={(e) => updateStep(i, "body", e.target.value)}
                  placeholder="Hi {{name}}, just checking in…"
                />
              </div>
            </div>
          ))}

          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? "Saving…" : "Create sequence"}
          </button>
        </form>
      )}

      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {Array.from({ length: 3 }).map((_, i) => (
            <div className="panel panel-pad" key={i}>
              <Skeleton width="40%" height={16} />
              <Skeleton width="20%" height={12} style={{ marginTop: 10 }} />
            </div>
          ))}
        </div>
      ) : list.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={<IconSequence size={22} />}
            title="No sequences yet"
            message="Build a follow-up sequence to automatically re-engage leads."
            action={
              <button className="btn" onClick={() => setShowForm(true)}>
                <IconPlus size={15} />
                New sequence
              </button>
            }
          />
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {list.map((seq) => (
            <div className="panel panel-pad" key={seq.id}>
              <div className="spread">
                <div>
                  <h3 style={{ fontSize: 15 }}>{seq.name}</h3>
                  <p className="faint" style={{ fontSize: 12.5, marginTop: 3 }}>
                    {(seq.steps?.length ?? 0)} step
                    {(seq.steps?.length ?? 0) === 1 ? "" : "s"}
                  </p>
                </div>
                <Badge tone={seq.is_active ? "green" : "neutral"} dot={seq.is_active}>
                  {seq.is_active ? "Active" : "Inactive"}
                </Badge>
              </div>
              {seq.steps?.length > 0 && (
                <div
                  className="row"
                  style={{ marginTop: 14, flexWrap: "wrap", gap: 8 }}
                >
                  {seq.steps.map((s) => (
                    <span className="badge badge-neutral" key={s.id}>
                      +{s.delay_hours}h · {s.action}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
