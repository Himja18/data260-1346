import AuthPanel from "./Authpanel.jsx";

// Shown on every protected page when there is no valid session.
export default function LoginRequired({ action = "continue", onLogin }) {
  return (
    <AuthPanel
      title="Login required"
      message={`Log in with your dispatcher account to ${action}.`}
      onLogin={onLogin}
    />
  );
}