// Axios instance for the FastAPI backend. Vite proxies /api and /auth -> 127.0.0.1:8446.
// HW7: the backend uses JWT bearer auth, so every request carries
// "Authorization: Bearer <token>". The token is kept in sessionStorage (cleared when
// the tab closes) and never in a cookie or localStorage.
import axios from "axios";

const TOKEN_KEY = "s1346_access_token";

export function getToken() {
  try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(token) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch { /* storage blocked: token lives only for this request cycle */ }
}

export const client = axios.create({
  baseURL: "/api",
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

client.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Turn FastAPI error bodies into one readable message + status code.
export function toError(err) {
  const status = err.response?.status ?? 0;
  const detail = err.response?.data?.detail;
  let message;
  if (typeof detail === "string") message = detail;
  else if (Array.isArray(detail)) message = detail.map((d) => d.msg).join("; ");
  else message = err.code === "ECONNABORTED" ? "Request timed out" : err.message;
  return { status, message };
}
