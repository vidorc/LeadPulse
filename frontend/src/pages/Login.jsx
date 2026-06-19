import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { auth, tokenStore, errorMessage } from "../services/api";
import { IconPulse } from "../components/icons";

/**
 * Combined Login / Signup screen.
 * On success, stores tokens and routes to the dashboard.
 */
export default function Login() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("login"); // "login" | "signup"
  const [form, setForm] = useState({
    email: "",
    password: "",
    full_name: "",
    org_name: "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isSignup = mode === "signup";
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const tokens = isSignup
        ? await auth.signup({
            email: form.email,
            password: form.password,
            org_name: form.org_name,
            full_name: form.full_name || undefined,
          })
        : await auth.login({
            email: form.email,
            password: form.password,
          });
      tokenStore.set(tokens);
      navigate("/dashboard");
    } catch (err) {
      setError(errorMessage(err, "Authentication failed."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-brand">
          <span className="brand-mark" aria-hidden="true">
            <IconPulse size={18} />
          </span>
          <span className="brand-name">LeadPulse</span>
        </div>

        <h1>{isSignup ? "Create your workspace" : "Welcome back"}</h1>
        <p className="sub">
          {isSignup
            ? "Start recovering revenue that slips through the cracks."
            : "Sign in to your Revenue Recovery workspace."}
        </p>

        {error && (
          <div className="auth-error" role="alert">
            {error}
          </div>
        )}

        {isSignup && (
          <>
            <div className="field">
              <label htmlFor="full_name">Full name</label>
              <input
                id="full_name"
                className="input"
                value={form.full_name}
                onChange={set("full_name")}
                placeholder="Ada Lovelace"
                autoComplete="name"
              />
            </div>
            <div className="field">
              <label htmlFor="org_name">Organization</label>
              <input
                id="org_name"
                className="input"
                value={form.org_name}
                onChange={set("org_name")}
                placeholder="Acme Inc."
                required
                autoComplete="organization"
              />
            </div>
          </>
        )}

        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            className="input"
            value={form.email}
            onChange={set("email")}
            placeholder="you@company.com"
            required
            autoComplete="email"
          />
        </div>

        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            className="input"
            value={form.password}
            onChange={set("password")}
            placeholder={isSignup ? "At least 8 characters" : "••••••••"}
            required
            minLength={isSignup ? 8 : undefined}
            autoComplete={isSignup ? "new-password" : "current-password"}
          />
        </div>

        <button
          type="submit"
          className="btn btn-primary"
          style={{ width: "100%", marginTop: 4 }}
          disabled={submitting}
        >
          {submitting
            ? "Please wait…"
            : isSignup
              ? "Create workspace"
              : "Sign in"}
        </button>

        <div className="auth-toggle">
          {isSignup ? "Already have an account?" : "New to LeadPulse?"}{" "}
          <button
            type="button"
            onClick={() => {
              setMode(isSignup ? "login" : "signup");
              setError("");
            }}
          >
            {isSignup ? "Sign in" : "Create one"}
          </button>
        </div>
      </form>
    </div>
  );
}
