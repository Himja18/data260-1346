import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import LoginRequired from "./LoginRequired.jsx";
import IncidentFields from "./IncidentFields.jsx";

export default function UpdateRecord({ user, onUpdate, onLogin }) {
  const [params] = useSearchParams();
  const id = params.get("id");

  const [routeTitle, setRouteTitle] = useState("");
  const [category, setCategory] = useState("");
  const [lineId, setLineId] = useState(null);
  const [loadState, setLoadState] = useState("loading");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  // Load the current values so the form starts pre-filled.
  useEffect(() => {
    if (!user || !id) return;
    let cancelled = false;
    setLoadState("loading");
    api
      .getIncident(id)
      .then((inc) => {
        if (cancelled) return;
        setRouteTitle(inc.route_title);
        setCategory(inc.category);
        setLineId(inc.line_id);
        setLoadState("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message);
        setLoadState("error");
      });
    return () => { cancelled = true; };
  }, [user, id]);

   if (!user) return <LoginRequired action="edit incidents" onLogin={onLogin} />;
  if (!id) {
    return (
      <p className="state">
        Pick an incident to edit from the list. <Link to="/">Go to incidents</Link>
      </p>
    );
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      // Keep line_id so editing the two fields doesn't unlink the transit line.
      await onUpdate(id, { route_title: routeTitle.trim(), category: category.trim(), line_id: lineId });
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <section className="form-card">
      <h1>Edit incident #{id}</h1>
      <p className="lede">Changes are saved to the incident log right away.</p>
      {loadState === "loading" && <p className="state">Loading incident…</p>}
      {error && <p className="alert alert-error" role="alert">{error}</p>}
      {loadState === "ready" && (
        <form onSubmit={handleSubmit}>
          <IncidentFields
            routeTitle={routeTitle} setRouteTitle={setRouteTitle}
            category={category} setCategory={setCategory}
          />
          <div className="form-actions">
            <button className="btn" type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save changes"}
            </button>
            <Link className="btn btn-quiet" to="/">Cancel</Link>
          </div>
        </form>
      )}
      {loadState === "error" && <Link className="btn btn-quiet" to="/">Back to incidents</Link>}
    </section>
  );
}
