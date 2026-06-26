import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
    baseURL: API,
    headers: { "Cache-Control": "no-cache", Pragma: "no-cache" },
});

// NOTE: localStorage tokens are vulnerable to XSS. Migrate to httpOnly cookies when possible.
api.interceptors.request.use((config) => {
    const token = localStorage.getItem("caa_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

api.interceptors.response.use(
    (r) => r,
    (err) => {
        if (err?.response?.status === 401) {
            localStorage.removeItem("caa_token");
            localStorage.removeItem("caa_user");
            window.dispatchEvent(new Event("auth:logout"));
        }
        return Promise.reject(err);
    },
);
