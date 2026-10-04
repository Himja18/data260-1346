import { useState } from "react";
import { useDispatch } from "react-redux";
import { Link, useNavigate } from "react-router-dom";
import { createIncident } from "../store/incidentsSlice.js";
import LoginRequired from "./LoginRequired.jsx";
import IncidentFields, { toPayload } from "./IncidentFields.jsx";

const EMPTY = { route_title: "", category: "", passengers_affected: 0, line_id: "" };

export default function CreateRecord({ user, onLogin }) {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  if (!user) return <LoginRequired action="report an incident" onLogin={onLogin} />;

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      // POST via the createIncident thunk; the slice adds the new record to state.
      await dispatch(createIncident(toPayload(form))).unwrap();
      navigate("/");                       // Home shows it straight from Redux
    } catch (err) {
      setError(err.message);               // rejectWithValue payload {status, message}
      setSaving(false);
    }
  }

  return (
    <section className="form-card">
      <h1>Report an incident</h1>
      <p className="lede">The server assigns the next incident code (INC-xxxxxx) automatically.</p>
      {error && <p className="alert alert-error" role="alert">{error}</p>}
      <form onSubmit={handleSubmit}>
        <IncidentFields form={form} setForm={setForm} />
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
