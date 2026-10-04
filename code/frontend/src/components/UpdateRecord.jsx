import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { selectIncidents, updateIncident } from "../store/incidentsSlice.js";
import { client, toError } from "../store/client.js";
import LoginRequired from "./LoginRequired.jsx";
import IncidentFields, { toPayload } from "./IncidentFields.jsx";

export default function UpdateRecord({ user, onLogin }) {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const incidents = useSelector(selectIncidents);

  const [selectedId, setSelectedId] = useState(params.get("id") ?? "");
  const [form, setForm] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  // Pre-fill the form for the selected ID: from Redux if loaded, else from the API.
  useEffect(() => {
    if (!user || !selectedId) { setForm(null); return; }
    setError("");
    const fromStore = incidents.find((x) => x.id === Number(selectedId));
    const fill = (inc) => setForm({
      route_title: inc.route_title, category: inc.category,
      passengers_affected: inc.passengers_affected, line_id: inc.line_id ?? "",
      incident_code: inc.incident_code,
    });
    if (fromStore) { fill(fromStore); return; }
    let cancelled = false;
    client.get(`/incidents/${selectedId}`)
      .then((res) => { if (!cancelled) fill(res.data); })
      .catch((err) => { if (!cancelled) { setForm(null); setError(toError(err).message); } });
    return () => { cancelled = true; };
  }, [user, selectedId, incidents]);

  if (!user) return <LoginRequired action="edit incidents" onLogin={onLogin} />;

  function selectId(id) {
    setSelectedId(id);
    setParams(id ? { id } : {});
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      // PUT /incidents/{id} via the updateIncident thunk; the slice replaces it in state.
      await dispatch(updateIncident({ id: selectedId, data: toPayload(form) })).unwrap();
      navigate("/");
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <section className="form-card">
      <h1>Update an incident</h1>
      <p className="lede">Select an incident by ID, edit it, and save.</p>

      <div className="field">
        <label htmlFor="select_id">Incident ID</label>
        <input id="select_id" type="number" min={1} list="incident-ids" value={selectedId}
          onChange={(e) => selectId(e.target.value)} placeholder="Type or pick an ID" />
        <datalist id="incident-ids">
          {incidents.map((inc) => (
            <option key={inc.id} value={inc.id}>{inc.incident_code} – {inc.route_title}</option>
          ))}
        </datalist>
      </div>

      {error && <p className="alert alert-error" role="alert">{error}</p>}

      {form && (
        <form onSubmit={handleSubmit}>
          <p className="lede">Editing <strong>{form.incident_code}</strong></p>
          <IncidentFields form={form} setForm={setForm} />
          <div className="form-actions">
            <button className="btn" type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save changes"}
            </button>
            <Link className="btn btn-quiet" to="/">Cancel</Link>
          </div>
        </form>
      )}
    </section>
  );
}
