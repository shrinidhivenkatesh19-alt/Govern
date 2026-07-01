import { useState } from "react";
import { Link } from "react-router-dom";
import { API } from "@/lib/api";

export default function ForgotPassword() {
    const [email, setEmail] = useState("");
    const [submitted, setSubmitted] = useState(false);
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            await fetch(`${API}/auth/forgot-password`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email }),
            });
        } finally {
            setLoading(false);
            setSubmitted(true);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-background px-4">
            <div className="w-full max-w-sm border border-border p-8">
                <h1 className="font-display text-2xl font-bold mb-2">Reset your password</h1>
                {submitted ? (
                    <p className="text-sm text-muted-foreground mt-4">
                        If that email exists, a reset link has been sent. Check your inbox.
                    </p>
                ) : (
                    <form onSubmit={handleSubmit} className="mt-6 space-y-4">
                        <input
                            type="email"
                            required
                            placeholder="you@company.com"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            data-testid="forgot-email-input"
                            className="w-full border border-border px-3 py-2 text-sm bg-background"
                        />
                        <button
                            type="submit"
                            disabled={loading}
                            data-testid="forgot-submit-btn"
                            className="w-full bg-[#0A0A0A] text-white py-2 text-sm uppercase tracking-wider"
                        >
                            {loading ? "Sending..." : "Send reset link"}
                        </button>
                    </form>
                )}
                <Link to="/login" className="block mt-6 text-xs text-muted-foreground underline">
                    Back to login
                </Link>
            </div>
        </div>
    );
}