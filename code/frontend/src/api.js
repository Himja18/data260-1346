// Thin wrapper around the FastAPI backend. credentials: "include" sends the
// HTTP-only session cookie; JavaScript never reads or stores the token itself.

function messageFrom(data, status) {
  if (data && typeof data.detail === "string") return data.detail;
  if (data && Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join("; ");
  return `Request failed (${status})`;
}

async function request(path, { headers, ...options } = {}) {
  const res = await fetch(`/api${path}`, {
    credentials: "include",
    ...options,
    headers: { "Content-Type": "application/json", ...(headers || {}) },
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(messageFrom(data, res.status));
    err.status = res.status;
    throw err;
  }
  return data;
}

export const api = {
  me: () => request("/auth/me"),
  login: (email, password) =>
    request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request("/auth/logout", { method: "POST" }),

  // Incident CRUD moved to Redux thunks (store/incidentsSlice.js, axios).
};
