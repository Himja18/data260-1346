import { useState } from "react";

// Username + password login form (HW7). onLogin (from App) calls POST /auth/login;
// on success the JWT is stored for the tab and App redirects to the home page.
export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await onLogin(username.trim(), password);
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="login-form">
      {error && <p className="alert alert-error" role="alert">{error}</p>}
      <div className="field">
        <label htmlFor="username">Username <span className="req">Required</span></label>
        <input
          id="username"
          type="text"
          autoComplete="username"
          placeholder="e.g., writer1346"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
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