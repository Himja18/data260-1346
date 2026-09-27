import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import LoginRequired from "./LoginRequired.jsx";
import CategoryPill from "./CategoryPill.jsx";

export default function DeleteRecord({ user, onDelete, onLogin }) {
  const [params] = useSearchParams();
  const id = params.get("id");

  const [incident, setIncident] = useState(null);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(false);

  // Show which incident is about to be deleted before the user confirms.
  useEffect(() => {
    if (!user || !id) return;
    let cancelled = false;
    api
      .getIncident(id)
      .then((inc) => { if (!cancelled) setIncident(inc); })
      .catch((err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [user, id]);

  if (!user) return <LoginRequired action="delete incidents" onLogin={onLogin} />;
  if (!id) {
    return (
      <p className="state">
        Pick an incident to delete from the list. <Link to="/">Go to incidents</Link>
      </p>
    );
  }

  async function handleDelete() {
    setError("");
    setDeleting(true);
    try {
      await onDelete(id);
    } catch (err) {
      setError(err.message);
      setDeleting(false);
    }
  }

  return (
    <section className="form-card">
      <h1>Delete incident #{id}</h1>
      <p className="lede">This removes the report from the incident log. It can't be undone.</p>
      {error && <p className="alert alert-error" role="alert">{error}</p>}
      {!incident && !error && <p className="state">Loading incident…</p>}
      {incident && (
        <>
          <div className="confirm-record">
            <p className="confirm-title">{incident.route_title}</p>
            <CategoryPill category={incident.category} />
          </div>
          <div className="form-actions">
            <button className="btn btn-danger" onClick={handleDelete} disabled={deleting}>
              {deleting ? "Deleting…" : "Delete"}
            </button>
            <Link className="btn btn-quiet" to="/">Keep it</Link>
          </div>
        </>
      )}
      {error && !incident && <Link className="btn btn-quiet" to="/">Back to incidents</Link>}
    </section>
  );
}
