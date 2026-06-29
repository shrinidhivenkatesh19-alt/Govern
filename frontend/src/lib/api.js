import axios from "axios";

/**
 * Resolve backend origin at runtime.
 * - Production (Vercel monorepo): leave REACT_APP_BACKEND_URL unset → same origin /api
 * - Split deploy (Vercel frontend + Railway backend): set REACT_APP_BACKEND_URL to Railway URL at build time
 * - Local dev: set REACT_APP_BACKEND_URL=http://localhost:8000 in frontend/.env
 */
export function getBackendUrl() {
    const fromEnv = process.env.REACT_APP_BACKEND_URL;
    if (fromEnv && String(fromEnv).trim() && fromEnv !== "undefined") {
        return String(fromEnv).replace(/\/$/, "");
    }
    if (typeof window !== "undefined") {
        return window.location.origin;
    }
    return "";
}

export const API = `${getBackendUrl()}/api`;

export const api = axios.create({
    baseURL: API,
    headers: { "Cache-Control": "no-cache", Pragma: "no-cache" },
});

api.interceptors.request.use((config) => {
    const token = localStorage.getItem("caa_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

api.interceptors.response.use(
    (r) => {
        const ct = r.headers?.["content-type"] || "";
        if (ct.includes("text/html") && !String(r.config?.url || "").includes("/auth/login")) {
            const err = new Error(
                "API returned HTML instead of JSON. Check Vercel Root Directory is repo root (not frontend/) " +
                    "or set REACT_APP_BACKEND_URL to your Railway backend URL.",
            );
            err.isApiMisconfigured = true;
            return Promise.reject(err);
        }
        return r;
    },
    (err) => {
        const url = err?.config?.url || "";
        const isAuthBootstrap = url.includes("/auth/me") || url.includes("/auth/login");
        if (err?.response?.status === 401 && !isAuthBootstrap) {
            localStorage.removeItem("caa_token");
            localStorage.removeItem("caa_user");
            window.dispatchEvent(new Event("auth:logout"));
        }
        return Promise.reject(err);
    },
);
