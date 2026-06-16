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
        const token = localStorage.getItem("caa_token");
        if (token && !user) {
            api.get("/auth/me")
                .then((r) => {
                    setUser(r.data);
                    localStorage.setItem("caa_user", JSON.stringify(r.data));
                })
                .catch(() => {})
                .finally(() => setLoading(false));
        } else {
            setLoading(false);
        }
    }, []);

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
