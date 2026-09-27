import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api.js";
import AuthPanel from "./components/Authpanel.jsx";
import Home from "./components/Home.jsx";
import CreateRecord from "./components/CreateRecord.jsx";
import UpdateRecord from "./components/UpdateRecord.jsx";
import DeleteRecord from "./components/DeleteRecord.jsx";

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [user, setUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [incidents, setIncidents] = useState([]);
  const [listState, setListState] = useState("idle"); // idle | loading | ready | error
  const [listError, setListError] = useState("");

  const loadIncidents = useCallback(async () => {
    setListState("loading");
    try {
      setIncidents(await api.listIncidents());
      setListState("ready");
    } catch (err) {
      if (err.status === 401) {
        setUser(null); // session expired on the server
        setListState("idle");
      } else {
        setListError(err.message);
        setListState("error");
      }
    }
  }, []);

  // On first load, ask the server whether the cookie maps to a live session.
  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setCheckingSession(false));
  }, []);

  // Whenever login state changes, (re)load or clear the list.
  useEffect(() => {
    if (user) loadIncidents();
    else setIncidents([]);
  }, [user, loadIncidents]);

  // Handlers passed down as props to the page components.
  async function handleLogin(email, password) {
    setUser(await api.login(email, password));
    // From the login page go home; from a protected page, stay where the user was.
    if (location.pathname === "/login") navigate("/");
  }

  async function handleLogout() {
    await api.logout().catch(() => {});
    setUser(null);
    navigate("/login");
  }

  async function handleCreate(data) {
    await api.createIncident(data);
    await loadIncidents();
    navigate("/");
  }

  async function handleUpdate(id, data) {
    await api.updateIncident(id, data);
    await loadIncidents();
    navigate("/");
  }

  async function handleDelete(id) {
    await api.deleteIncident(id);
    await loadIncidents();
    navigate("/");
  }

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand">
            <span className="brand-dot" aria-hidden="true" />
            Transit Incident Desk
          </Link>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end>Incidents</NavLink>
            {user && <NavLink to="/create">Report incident</NavLink>}
          </nav>
          <div className="session">
            {user ? (
              <>
                <span>{user.name}</span>
                <button className="btn btn-on-dark btn-small" onClick={handleLogout}>
                  Log out
                </button>
              </>
            ) : null /* logged out: every page already shows the login panel */}
          </div>
        </div>
        <div className="route-strip" aria-hidden="true">
          <span /><span /><span /><span />
        </div>
      </header>

      <main>
        {checkingSession ? (
          <p className="state">Checking your session…</p>
        ) : (
          <Routes>
            <Route
              path="/"
              element={
                <Home
                  user={user}
                  incidents={incidents}
                  listState={listState}
                  listError={listError}
                  onRetry={loadIncidents}
                  onLogin={handleLogin}
                />
              }
            />
            <Route
              path="/login"
              element={
                user ? (
                  <section className="gate">
                    <h2>You're logged in</h2>
                    <p>Signed in as {user.email}.</p>
                    <Link className="btn" to="/">Go to incidents</Link>
                  </section>
                ) : (
                  <AuthPanel
                    title="Welcome back"
                    message="Log in to view, report, edit, and remove transit incident reports."
                    onLogin={handleLogin}
                  />
                )
              }
            />
            <Route path="/create" element={<CreateRecord user={user} onCreate={handleCreate} onLogin={handleLogin} />} />
            <Route path="/update" element={<UpdateRecord user={user} onUpdate={handleUpdate} onLogin={handleLogin} />} />
            <Route path="/delete" element={<DeleteRecord user={user} onDelete={handleDelete} onLogin={handleLogin} />} />
            <Route path="*" element={<p className="state">That page doesn't exist. <Link to="/">Go to incidents</Link></p>} />
          </Routes>
        )}
      </main>

      <footer className="footer">DATA-260 HW4, s1346, Municipal Transit Incidents</footer>
    </>
  );
}