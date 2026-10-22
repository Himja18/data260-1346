// Thin wrapper around the FastAPI auth endpoints (HW7: JWT bearer tokens).
// /auth/login returns an access token; it is stored via setToken() and sent as
// "Authorization: Bearer ..." by both this helper and the axios client.
import { getToken, setToken } from "./store/client.js";

function messageFrom(data, status) {
  if (data && typeof data.detail === "string") return data.detail;
  if (data && Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join("; ");
  return `Request failed (${status})`;
}

async function request(url, { headers, ...options } = {}) {
  const token = getToken();
  const res = await fetch(url, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers || {}),
    },
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
  async login(username, password) {
    const tok = await request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setToken(tok.access_token);
    return request("/auth/me");
  },
  logout: async () => setToken(null),     // stateless JWT: forgetting the token logs out
  runBikeAgent: (formData) => request("/api/bike/run", { method: "POST", body: formData }),

  // Incident CRUD lives in Redux thunks (store/incidentsSlice.js, axios).
};
