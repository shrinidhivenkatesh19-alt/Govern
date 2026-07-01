import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { ShieldCheck, LogIn } from "lucide-react";

export default function Login() {
    const { login } = useAuth();
    const navigate = useNavigate();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [loading, setLoading] = useState(false);

    const onSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            await login(email, password);
            toast.success("Signed in");
            navigate("/app");
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Login failed");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen grid lg:grid-cols-2">
            <div className="hidden lg:flex flex-col justify-between p-12 bg-[#0A0A0A] text-white">
                <div className="flex items-center gap-2">
                    <div className="w-7 h-7 bg-white text-[#0A0A0A] flex items-center justify-center">
                        <ShieldCheck className="w-4 h-4" strokeWidth={2.25} />
                    </div>
                    <div>
                        <div className="font-display font-bold tracking-tight">GOVERN</div>
                        <div className="label-overline text-white/60 text-[10px]">Approval Agent</div>
                    </div>
                </div>

                <div className="space-y-6">
                    <div className="label-overline text-[#FFD700]">Why this exists</div>
                    <h1 className="font-display text-4xl lg:text-5xl font-bold tracking-tight leading-[1.05]">
                        Routine content shouldn't reach the CEO.
                        <br />
                        <span className="text-white/50">Innovation should.</span>
                    </h1>
                    <p className="text-white/70 max-w-md leading-relaxed">
                        The agent scores every brief, classifies routine vs. innovation, flags risk, and routes to the right tier — so CEO bandwidth goes to decisions only the CEO can make.
                    </p>

                    <div className="grid grid-cols-3 border-t border-white/10 pt-6">
                        <Stat label="Upstream delay" value="Solved" />
                        <Stat label="Middle bottleneck" value="Triaged" />
                        <Stat label="CEO trap" value="Bypassed" />
                    </div>
                </div>

                <div className="label-overline text-white/40 text-[10px]">v1 · Phase 1 + 2 MVP</div>
            </div>

            <div className="flex items-center justify-center p-8 lg:p-16 bg-white">
                <form onSubmit={onSubmit} className="w-full max-w-md" data-testid="login-form">
                    <div className="label-overline mb-3">Sign in</div>
                    <h2 className="font-display text-3xl font-bold tracking-tight mb-8">Enter the control room.</h2>

                    <label className="block mb-4">
                        <span className="label-overline block mb-2">Email</span>
                        <input
                            type="email"
                            required
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            data-testid="login-email-input"
                            className="w-full px-4 py-3 border border-border bg-white focus:outline-none focus:ring-2 focus:ring-[#002FA7] focus:ring-offset-1"
                        />
                    </label>

                    <label className="block mb-6">
                        <span className="label-overline block mb-2">Password</span>
    <input
        type="password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        data-testid="login-password-input"
        className="w-full px-4 py-3 border border-border bg-white focus:outline-none focus:ring-2 focus:ring-[#002FA7] focus:ring-offset-1"
    />
    <Link
        to="/forgot-password"
        className="block text-right text-xs text-muted-foreground underline mt-2 hover:text-[#002FA7]"
        data-testid="goto-forgot-password-link"
    >
        Forgot password?
    </Link>
                    </label>

                    <button
                        type="submit"
                        disabled={loading}
                        data-testid="login-submit-btn"
                        className="w-full flex items-center justify-center gap-2 py-3 bg-[#0A0A0A] text-white hover:bg-[#002FA7] transition-colors uppercase tracking-[0.18em] text-xs font-medium disabled:opacity-60"
                    >
                        <LogIn className="w-4 h-4" />
                        {loading ? "Signing in..." : "Sign in"}
                    </button>

                    <p className="text-sm text-muted-foreground mt-6">
                        New here?{" "}
                        <Link to="/register" className="underline text-[#0A0A0A] hover:text-[#002FA7]" data-testid="goto-register-link">
                            Create an account
                        </Link>
                    </p>
                </form>
            </div>
        </div>
    );
}

function Stat({ label, value }) {
    return (
        <div className="px-3">
            <div className="label-overline text-white/40 mb-1">{label}</div>
            <div className="font-display font-bold text-lg text-[#FFD700]">{value}</div>
        </div>
    );
}
