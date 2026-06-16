import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { UserPlus } from "lucide-react";

const roles = [
    { value: "submitter", label: "Submitter", desc: "Marketing rep submitting briefs" },
    { value: "reviewer", label: "Reviewer", desc: "Product team approver" },
    { value: "marketing_lead", label: "Marketing Lead", desc: "Escalation handler" },
    { value: "ceo", label: "CEO", desc: "Final tier — innovation & risk" },
];

export default function Register() {
    const { register } = useAuth();
    const navigate = useNavigate();
    const [form, setForm] = useState({ name: "", email: "", password: "", role: "submitter" });
    const [loading, setLoading] = useState(false);

    const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

    const onSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            await register(form);
            toast.success("Account created");
            navigate("/app");
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Registration failed");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-white flex items-center justify-center p-6 lg:p-12">
            <form onSubmit={onSubmit} className="w-full max-w-xl border border-border p-8 lg:p-10" data-testid="register-form">
                <div className="label-overline mb-3">Create account</div>
                <h2 className="font-display text-3xl font-bold tracking-tight mb-8">Join the approval chain.</h2>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                    <label className="block">
                        <span className="label-overline block mb-2">Full name</span>
                        <input
                            required
                            value={form.name}
                            onChange={(e) => set("name", e.target.value)}
                            data-testid="register-name-input"
                            className="w-full px-3 py-2.5 border border-border focus:outline-none focus:ring-2 focus:ring-[#002FA7]"
                        />
                    </label>
                    <label className="block">
                        <span className="label-overline block mb-2">Email</span>
                        <input
                            required
                            type="email"
                            value={form.email}
                            onChange={(e) => set("email", e.target.value)}
                            data-testid="register-email-input"
                            className="w-full px-3 py-2.5 border border-border focus:outline-none focus:ring-2 focus:ring-[#002FA7]"
                        />
                    </label>
                </div>

                <label className="block mb-5">
                    <span className="label-overline block mb-2">Password</span>
                    <input
                        required
                        type="password"
                        minLength={6}
                        value={form.password}
                        onChange={(e) => set("password", e.target.value)}
                        data-testid="register-password-input"
                        className="w-full px-3 py-2.5 border border-border focus:outline-none focus:ring-2 focus:ring-[#002FA7]"
                    />
                </label>

                <div className="mb-6">
                    <span className="label-overline block mb-2">Role</span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {roles.map((r) => (
                            <button
                                key={r.value}
                                type="button"
                                onClick={() => set("role", r.value)}
                                data-testid={`register-role-${r.value}`}
                                className={`text-left p-3 border transition-colors ${
                                    form.role === r.value ? "border-[#002FA7] bg-[#F3F4F6]" : "border-border hover:bg-[#F3F4F6]"
                                }`}
                            >
                                <div className="text-sm font-medium">{r.label}</div>
                                <div className="text-xs text-muted-foreground">{r.desc}</div>
                            </button>
                        ))}
                    </div>
                </div>

                <button
                    type="submit"
                    disabled={loading}
                    data-testid="register-submit-btn"
                    className="w-full flex items-center justify-center gap-2 py-3 bg-[#0A0A0A] text-white hover:bg-[#002FA7] transition-colors uppercase tracking-[0.18em] text-xs font-medium disabled:opacity-60"
                >
                    <UserPlus className="w-4 h-4" />
                    {loading ? "Creating..." : "Create account"}
                </button>

                <p className="text-sm text-muted-foreground mt-6">
                    Already have an account?{" "}
                    <Link to="/login" className="underline text-[#0A0A0A] hover:text-[#002FA7]" data-testid="goto-login-link">
                        Sign in
                    </Link>
                </p>
            </form>
        </div>
    );
}
