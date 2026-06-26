import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(() => {
        const u = localStorage.getItem("caa_user");
        return u ? JSON.parse(u) : null;
    });
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const onLogout = () => setUser(null);
        window.addEventListener("auth:logout", onLogout);
        return () => window.removeEventListener("auth:logout", onLogout);
    }, []);

    useEffect(() => {
        const token = localStorage.getItem("caa_token");
        if (!token) {
            if (user) {
                setUser(null);
                localStorage.removeItem("caa_user");
            }
            setLoading(false);
            return;
        }
        api.get("/auth/me")
            .then((r) => {
                setUser(r.data);
                localStorage.setItem("caa_user", JSON.stringify(r.data));
            })
            .catch(() => {
                localStorage.removeItem("caa_token");
                localStorage.removeItem("caa_user");
                setUser(null);
            })
            .finally(() => setLoading(false));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []); // validate stored token once on mount

    const login = async (email, password) => {
        const r = await api.post("/auth/login", { email, password });
        localStorage.setItem("caa_token", r.data.token);
        localStorage.setItem("caa_user", JSON.stringify(r.data.user));
        setUser(r.data.user);
        return r.data.user;
    };

    const register = async (payload) => {
        const r = await api.post("/auth/register", payload);
        localStorage.setItem("caa_token", r.data.token);
        localStorage.setItem("caa_user", JSON.stringify(r.data.user));
        setUser(r.data.user);
        return r.data.user;
    };

    const logout = () => {
        localStorage.removeItem("caa_token");
        localStorage.removeItem("caa_user");
        setUser(null);
    };

    return <AuthCtx.Provider value={{ user, loading, login, register, logout }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
