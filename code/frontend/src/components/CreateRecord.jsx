import { useState } from "react";
import { Link } from "react-router-dom";
import LoginRequired from "./LoginRequired.jsx";
import IncidentFields from "./IncidentFields.jsx";

export default function CreateRecord({ user, onCreate, onLogin }) {
  const [routeTitle, setRouteTitle] = useState("");
  const [category, setCategory] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  
  if (!user) return <LoginRequired action="report an incident" onLogin={onLogin} />;

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      // onCreate (from App) POSTs to the API, reloads the list, and redirects to "/".
      await onCreate({ route_title: routeTitle.trim(), category: category.trim() });
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <section className="form-card">
      <h1>Report an incident</h1>
      <p className="lede">The report gets the next incident number automatically.</p>
      {error && <p className="alert alert-error" role="alert">{error}</p>}
      <form onSubmit={handleSubmit}>
        <IncidentFields
          routeTitle={routeTitle} setRouteTitle={setRouteTitle}
          category={category} setCategory={setCategory}
        />
        <div className="form-actions">
          <button className="btn" type="submit" disabled={saving}>
            {saving ? "Reporting…" : "Report incident"}
          </button>
          <Link className="btn btn-quiet" to="/">Cancel</Link>
        </div>
      </form>
    </section>
  );
}
