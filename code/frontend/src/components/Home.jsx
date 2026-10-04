import { useDispatch, useSelector } from "react-redux";
import { Link } from "react-router-dom";
import { clearMessage, deleteIncident, fetchIncidents, selectIncidents }
  from "../store/incidentsSlice.js";
import LoginRequired from "./LoginRequired.jsx";
import CategoryPill from "./CategoryPill.jsx";

function formatTime(utcString) {
  // Backend stores naive UTC; mark it as UTC so the browser shows local time.
  return new Date(`${utcString}Z`).toLocaleString([], {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

export default function Home({ user, onLogin }) {
  const dispatch = useDispatch();
  // Everything below is read from the Redux store, so the table re-renders
  // automatically after any create / update / delete thunk succeeds.
  const incidents = useSelector(selectIncidents);
  const { status, error, lastAction } = useSelector((s) => s.incidents);

  if (!user) return <LoginRequired action="see and manage incident reports" onLogin={onLogin} />;

  function handleDelete(inc) {
    if (window.confirm(`Delete ${inc.incident_code}: "${inc.route_title}"?`)) {
      dispatch(deleteIncident(inc.id));
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Incident reports</h1>
          <p className="lede">Newest reports first, up to 50 at a time. {incidents.length} in Redux store.</p>
        </div>
        <Link className="btn" to="/create">Report incident</Link>
      </div>

      {lastAction && (
        <p className="alert" role="status" onClick={() => dispatch(clearMessage())}>{lastAction}</p>
      )}
      {error && status !== "error" && (
        <p className="alert alert-error" role="alert">{error.message}</p>
      )}

      <section className="board" aria-live="polite">
        {status === "loading" && <p className="state">Loading reports…</p>}

        {status === "error" && (
          <div className="state state-error">
            <p>{error?.message}</p>
            <button className="btn btn-quiet btn-small" onClick={() => dispatch(fetchIncidents())}>
              Try again
            </button>
          </div>
        )}

        {status === "ready" && incidents.length === 0 && (
          <div className="state">
            <p>No incidents have been reported yet.</p>
            <Link className="btn btn-small" to="/create">Report the first one</Link>
          </div>
        )}

        {status === "ready" && incidents.length > 0 && (
          <table>
            <thead>
              <tr>
                <th scope="col">Code</th>
                <th scope="col">Route and incident</th>
                <th scope="col">Category</th>
                <th scope="col">Passengers</th>
                <th scope="col">Line</th>
                <th scope="col">Reported</th>
                <th scope="col"><span className="visually-hidden">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((inc) => (
                <tr key={inc.id}>
                  <td data-label="Code" className="id-cell">{inc.incident_code}</td>
                  <td data-label="Route and incident" className="title-cell">{inc.route_title}</td>
                  <td data-label="Category"><CategoryPill category={inc.category} /></td>
                  <td data-label="Passengers">{inc.passengers_affected}</td>
                  <td data-label="Line">{inc.line_id ?? "–"}</td>
                  <td data-label="Reported" className="time-cell">{formatTime(inc.created_at)}</td>
                  <td className="actions-cell">
                    <div className="actions">
                      <Link className="btn btn-quiet btn-small" to={`/update?id=${inc.id}`}>Edit</Link>
                      <button className="btn btn-quiet btn-small btn-danger-quiet"
                        onClick={() => handleDelete(inc)}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
