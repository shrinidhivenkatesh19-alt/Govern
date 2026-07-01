import { useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { API } from "@/lib/api";

export default function ResetPassword() {
    const [params] = useSearchParams();
    const navigate = useNavigate();
    const token = params.get("token");

    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError("");
        if (password !== confirm) {
            setError("Passwords don't match.");
            return;
        }
        setLoading(true);
        try {
            const res = await fetch(`${API}/auth/reset-password`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token, new_password: password }),
            });
            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.detail || "Reset failed.");
            }
            navigate("/login", { state: { resetSuccess: true } });
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    if (!token) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background px-4">
                <div className="w-full max-w-sm border border-border p-8 text-center">
                    <p className="text-sm text-muted-foreground">Missing reset token.</p>
                    <Link to="/forgot-password" className="block mt-4 text-xs underline">
                        Request a new link
                    </Link>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-background px-4">
            <div className="w-full max-w-sm border border-border p-8">
                <h1 className="font-display text-2xl font-bold mb-6">Set a new password</h1>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <input
                        type="password"
                        required
                        placeholder="New password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        data-testid="reset-password-input"
                        className="w-full border border-border px-3 py-2 text-sm bg-background"
                    />
                    <input
                        type="password"
                        required
                        placeholder="Confirm password"
                        value={confirm}
                        onChange={(e) => setConfirm(e.target.value)}
                        data-testid="reset-confirm-input"
                        className="w-full border border-border px-3 py-2 text-sm bg-background"
                    />
                    {error && <p className="text-xs text-[#FF3B1F]">{error}</p>}
                    <button
                        type="submit"
                        disabled={loading}
                        data-testid="reset-submit-btn"
                        className="w-full bg-[#0A0A0A] text-white py-2 text-sm uppercase tracking-wider"
                    >
                        {loading ? "Updating..." : "Reset password"}
                    </button>
                </form>
                <Link to="/forgot-password" className="block mt-6 text-xs text-muted-foreground underline">
                    Need a new link?
                </Link>
            </div>
        </div>
    );
}