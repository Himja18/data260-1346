import Login from "./Login.jsx";

// Login screen in the HW1 transit-signage style: masthead, route strip, card.
export default function AuthPanel({ title = "Login required", message, onLogin }) {
  return (
    <section className="auth-screen">
      <div className="auth-wrap">
        <div className="masthead">
          <span className="line-dot" aria-hidden="true" />
          <span className="eyebrow">Route 2 · Dispatcher Desk</span>
        </div>
        <h1 className="auth-title">{title}</h1>
        <p className="auth-sub">{message}</p>
        <div className="route-strip" aria-hidden="true">
          <span></span><span></span><span></span><span></span>
        </div>
        <div className="auth-card">
          <Login onLogin={onLogin} />
        </div>
      </div>
    </section>
  );
}