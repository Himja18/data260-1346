import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api.js";
import { clearIncidents, fetchIncidents } from "./store/incidentsSlice.js";
import AuthPanel from "./components/Authpanel.jsx";
import Home from "./components/Home.jsx";
import CreateRecord from "./components/CreateRecord.jsx";
import UpdateRecord from "./components/UpdateRecord.jsx";

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useDispatch();
  const [user, setUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);
  // Incident data now lives in Redux (store/incidentsSlice.js), not in App state.
  const incidentsError = useSelector((s) => s.incidents.error);

  // On first load, ask the server whether the cookie maps to a live session.
  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setCheckingSession(false));
  }, []);

  // Whenever login state changes, load or clear the incidents in the store.
  useEffect(() => {
    if (user) dispatch(fetchIncidents());
    else dispatch(clearIncidents());
  }, [user, dispatch]);

  // Any thunk that comes back 401 means the server-side session expired.
  useEffect(() => {
    if (incidentsError?.status === 401) setUser(null);
  }, [incidentsError]);

  async function handleLogin(email, password) {
    setUser(await api.login(email, password));
    if (location.pathname === "/login") navigate("/");
  }

  async function handleLogout() {
    await api.logout().catch(() => {});
    setUser(null);
    navigate("/login");
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
            {user && <NavLink to="/update">Update incident</NavLink>}
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
                <Home user={user} onLogin={handleLogin} />
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
            <Route path="/create" element={<CreateRecord user={user} onLogin={handleLogin} />} />
            <Route path="/update" element={<UpdateRecord user={user} onLogin={handleLogin} />} />
            <Route path="*" element={<p className="state">That page doesn't exist. <Link to="/">Go to incidents</Link></p>} />
          </Routes>
        )}
      </main>

      <footer className="footer">DATA-260 HW5, s1346, Municipal Transit Incidents</footer>
    </>
  );
}