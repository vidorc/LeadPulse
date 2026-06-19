import { useState } from "react";
import { leads as leadsApi, errorMessage } from "../services/api";
import useFetch from "../hooks/useFetch";
import {
  RowSkeleton,
  ErrorState,
  EmptyState,
  StatusBadge,
  Badge,
} from "../components/ui";
import { formatRelative } from "../utils/format";
import { IconPlus, IconClose, IconLeads } from "../components/icons";

const EMPTY_FORM = {
  name: "",
  email: "",
  phone: "",
  source: "web",
  message: "",
};

export default function Leads() {
  const { data, loading, error, refetch, setData } = useFetch(
    leadsApi.list,
    []
  );
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  const rows = data || [];
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setFormError("");
    setSubmitting(true);
    try {
      const created = await leadsApi.create({
        name: form.name,
        email: form.email || undefined,
        phone: form.phone || undefined,
        source: form.source,
        message: form.message || undefined,
      });
      setData([created, ...(data || [])]);
      setForm(EMPTY_FORM);
      setShowForm(false);
    } catch (err) {
      setFormError(errorMessage(err, "Could not create lead."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Leads</h1>
          <p className="sub">Every inbound, scored and routed.</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setShowForm((s) => !s)}
        >
          {showForm ? <IconClose size={16} /> : <IconPlus size={16} />}
          {showForm ? "Cancel" : "New lead"}
        </button>
      </div>

      {showForm && (
        <form className="panel panel-pad" onSubmit={submit} style={{ marginBottom: 20 }}>
          {formError && (
            <div className="auth-error" role="alert" style={{ marginBottom: 14 }}>
              {formError}
            </div>
          )}
          <div className="grid-2">
            <div className="field">
              <label htmlFor="l-name">Name</label>
              <input
                id="l-name"
                className="input"
                value={form.name}
                onChange={set("name")}
                placeholder="Jane Cooper"
                required
              />
            </div>
            <div className="field">
              <label htmlFor="l-source">Source</label>
              <select
                id="l-source"
                className="input"
                value={form.source}
                onChange={set("source")}
              >
                <option value="web">Web form</option>
                <option value="referral">Referral</option>
                <option value="ads">Ads</option>
                <option value="email">Email</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="l-email">Email</label>
              <input
                id="l-email"
                type="email"
                className="input"
                value={form.email}
                onChange={set("email")}
                placeholder="jane@company.com"
              />
            </div>
            <div className="field">
              <label htmlFor="l-phone">Phone</label>
              <input
                id="l-phone"
                className="input"
                value={form.phone}
                onChange={set("phone")}
                placeholder="+1 555 0100"
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="l-message">Message</label>
            <textarea
              id="l-message"
              className="input"
              value={form.message}
              onChange={set("message")}
              placeholder="What does the lead need?"
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? "Saving…" : "Create lead"}
          </button>
        </form>
      )}

      <div className="panel">
        {error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : !loading && rows.length === 0 ? (
          <EmptyState
            icon={<IconLeads size={22} />}
            title="No leads yet"
            message="Once leads start coming in, they'll show up here."
            action={
              <button className="btn" onClick={() => setShowForm(true)}>
                <IconPlus size={15} />
                Add your first lead
              </button>
            }
          />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Decision</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {loading
                  ? Array.from({ length: 6 }).map((_, i) => (
                      <RowSkeleton key={i} cols={5} />
                    ))
                  : rows.map((lead) => (
                      <tr key={lead.id}>
                        <td>
                          <div className="primary">{lead.name || "—"}</div>
                          {lead.email && (
                            <div className="faint" style={{ fontSize: 12 }}>
                              {lead.email}
                            </div>
                          )}
                        </td>
                        <td>{lead.source || "—"}</td>
                        <td>
                          {lead.status ? (
                            <StatusBadge value={lead.status} />
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>
                          {lead.decision ? (
                            <Badge tone="neutral">
                              {String(lead.decision).replace(/_/g, " ")}
                            </Badge>
                          ) : (
                            <span className="faint">Pending</span>
                          )}
                        </td>
                        <td>{formatRelative(lead.created_at)}</td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
