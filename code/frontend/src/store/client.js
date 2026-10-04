// Axios instance for the FastAPI backend. Vite proxies /api -> 127.0.0.1:8446,
// and withCredentials sends the HTTP-only session cookie on every request.
import axios from "axios";

export const client = axios.create({
  baseURL: "/api",
  withCredentials: true,
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
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
