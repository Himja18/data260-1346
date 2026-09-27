import { Link } from "react-router-dom";
import LoginRequired from "./LoginRequired.jsx";
import CategoryPill from "./CategoryPill.jsx";

function formatTime(utcString) {
  // Backend stores naive UTC; mark it as UTC so the browser shows local time.
  return new Date(`${utcString}Z`).toLocaleString([], {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

export default function Home({ user, incidents, listState, listError, onRetry, onLogin }) {
   if (!user) return <LoginRequired action="see and manage incident reports" onLogin={onLogin} />;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Incident reports</h1>
          <p className="lede">Newest reports first, up to 50 at a time.</p>
        </div>
        <Link className="btn" to="/create">Report incident</Link>
      </div>

      <section className="board" aria-live="polite">
        {listState === "loading" && <p className="state">Loading reports…</p>}

        {listState === "error" && (
          <div className="state state-error">
            <p>{listError}</p>
            <button className="btn btn-quiet btn-small" onClick={onRetry}>Try again</button>
          </div>
        )}

        {listState === "ready" && incidents.length === 0 && (
          <div className="state">
            <p>No incidents have been reported yet.</p>
            <Link className="btn btn-small" to="/create">Report the first one</Link>
          </div>
        )}

        {listState === "ready" && incidents.length > 0 && (
          <table>
            <thead>
              <tr>
                <th scope="col">ID</th>
                <th scope="col">Route and incident</th>
                <th scope="col">Category</th>
                <th scope="col">Reported</th>
                <th scope="col"><span className="visually-hidden">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((inc) => (
                <tr key={inc.id}>
                  <td data-label="ID" className="id-cell">#{inc.id}</td>
                  <td data-label="Route and incident" className="title-cell">{inc.route_title}</td>
                  <td data-label="Category"><CategoryPill category={inc.category} /></td>
                  <td data-label="Reported" className="time-cell">{formatTime(inc.created_at)}</td>
                  <td className="actions">
                    <Link className="btn btn-quiet btn-small" to={`/update?id=${inc.id}`}>Edit</Link>
                    <Link className="btn btn-quiet btn-small btn-danger-quiet" to={`/delete?id=${inc.id}`}>Delete</Link>
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
