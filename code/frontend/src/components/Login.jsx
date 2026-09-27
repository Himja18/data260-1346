import { useState } from "react";

// Email + password login form. onLogin (from App) calls the API; on success the
// backend sets the HTTP-only session cookie and App redirects to the home page.
export default function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await onLogin(email.trim(), password);
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="login-form">
      {error && <p className="alert alert-error" role="alert">{error}</p>}
      <div className="field">
        <label htmlFor="email">Email <span className="req">Required</span></label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          placeholder="e.g., dispatcher1346@transit.test"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoFocus
        />
      </div>
      <div className="field">
        <label htmlFor="password">Password <span className="req">Required</span></label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </div>
      <button className="btn btn-block" type="submit" disabled={submitting}>
        {submitting ? "Logging in…" : "Log in"}
      </button>
    </form>
  );
}