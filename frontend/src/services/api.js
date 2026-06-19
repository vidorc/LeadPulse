import axios from "axios";

/**
 * Base URL: backend mounts all routes under /api/v1 (see app/main.py).
 * Override with VITE_API_BASE if the API lives elsewhere.
 */
const BASE_URL =
  import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api/v1";

const ACCESS_KEY = "lp_access_token";
const REFRESH_KEY = "lp_refresh_token";

/* ----------------------------- token storage ----------------------------- */
export const tokenStore = {
  get: () => localStorage.getItem(ACCESS_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  set: ({ access_token, refresh_token }) => {
    if (access_token) localStorage.setItem(ACCESS_KEY, access_token);
    if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
  },
  clear: () => {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
  isAuthed: () => Boolean(localStorage.getItem(ACCESS_KEY)),
};

/* ------------------------------ axios client ------------------------------ */
const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) config.headers["Authorization"] = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (error) => {
    const status = error?.response?.status;
    // On expired / missing auth, drop tokens and bounce to login —
    // but never loop on the auth endpoints themselves.
    const url = error?.config?.url || "";
    const isAuthCall = url.includes("/auth/");
    if (status === 401 && !isAuthCall) {
      tokenStore.clear();
      if (!window.location.pathname.startsWith("/login")) {
        window.location.assign("/login");
      }
    }
    return Promise.reject(error);
  }
);

/**
 * Normalize an axios error into a human-readable message.
 * The API wraps errors in an envelope: { error: { type, message, request_id } }
 * where `message` is a string for http errors and an array of
 * {msg, loc} objects for validation (422) errors. We also tolerate the bare
 * FastAPI { detail } shape for any endpoint not yet behind the envelope.
 */
export function errorMessage(err, fallback = "Something went wrong.") {
  const data = err?.response?.data;
  const payload = data?.error?.message ?? data?.detail;
  if (typeof payload === "string") return payload;
  if (Array.isArray(payload) && payload.length) {
    return payload.map((d) => d.msg || JSON.stringify(d)).join(", ");
  }
  if (err?.message === "Network Error") {
    return "Cannot reach the server. Is the API running?";
  }
  return err?.message || fallback;
}

/** Optional: surface the server request id for support/debugging. */
export function errorRequestId(err) {
  return err?.response?.data?.error?.request_id ?? null;
}

/* ------------------------------- endpoints -------------------------------- */
export const auth = {
  signup: (body) => api.post("/auth/signup", body).then((r) => r.data),
  login: (body) => api.post("/auth/login", body).then((r) => r.data),
  me: () => api.get("/auth/me").then((r) => r.data),
};

export const leads = {
  list: () => api.get("/leads/").then((r) => r.data),
  create: (body) => api.post("/leads/", body).then((r) => r.data),
  summary: () => api.get("/leads/dashboard/summary").then((r) => r.data),
  reviewQueue: () => api.get("/leads/review-queue").then((r) => r.data),
};

export const opportunities = {
  list: () => api.get("/opportunities/").then((r) => r.data),
  create: (body) => api.post("/opportunities/", body).then((r) => r.data),
  setStage: (id, stage) =>
    api.post(`/opportunities/${id}/stage`, { stage }).then((r) => r.data),
};

export const leaks = {
  alerts: () => api.get("/leak-detection/alerts").then((r) => r.data),
  scan: () => api.post("/leak-detection/scan").then((r) => r.data),
  policies: () => api.get("/leak-detection/policies").then((r) => r.data),
};

export const sequences = {
  list: () => api.get("/follow-ups/sequences").then((r) => r.data),
  create: (body) =>
    api.post("/follow-ups/sequences", body).then((r) => r.data),
};

export default api;
