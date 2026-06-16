import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { LayoutDashboard, FilePlus2, Inbox, BarChart3, LogOut, ShieldCheck } from "lucide-react";

const navItems = [
    { to: "/app", label: "Overview", icon: LayoutDashboard, end: true, testid: "nav-overview" },
    { to: "/app/submit", label: "New Submission", icon: FilePlus2, testid: "nav-submit" },
    { to: "/app/queue", label: "Approval Queue", icon: Inbox, testid: "nav-queue" },
    { to: "/app/analytics", label: "Governance", icon: BarChart3, testid: "nav-analytics" },
];

const roleLabel = {
    submitter: "Submitter",
    reviewer: "Reviewer · Product",
    marketing_lead: "Marketing Lead",
    ceo: "CEO",
};

export default function Shell() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const doLogout = () => {
        logout();
        navigate("/login");
    };

    return (
        <div className="min-h-screen flex bg-white" data-testid="app-shell">
            <aside className="w-64 border-r border-border bg-white flex flex-col" data-testid="sidebar">
                <div className="px-6 py-6 border-b border-border">
                    <div className="flex items-center gap-2">
                        <div className="w-7 h-7 bg-[#0A0A0A] flex items-center justify-center">
                            <ShieldCheck className="w-4 h-4 text-white" strokeWidth={2} />
                        </div>
                        <div>
                            <div className="font-display font-bold text-base leading-none tracking-tight">GOVERN</div>
                            <div className="label-overline mt-1 text-[10px]">Approval Agent</div>
                        </div>
                    </div>
                </div>

                <nav className="flex-1 py-4">
                    {navItems.map((item) => (
                        <NavLink
                            key={item.to}
                            to={item.to}
                            end={item.end}
                            data-testid={item.testid}
                            className={({ isActive }) =>
                                `flex items-center gap-3 px-6 py-3 text-sm border-l-2 transition-colors ${
                                    isActive
                                        ? "border-[#002FA7] bg-[#F3F4F6] text-[#0A0A0A] font-medium"
                                        : "border-transparent text-muted-foreground hover:bg-[#F3F4F6] hover:text-[#0A0A0A]"
                                }`
                            }
                        >
                            <item.icon className="w-4 h-4" strokeWidth={1.75} />
                            {item.label}
                        </NavLink>
                    ))}
                </nav>

                <div className="border-t border-border p-4">
                    <div className="flex items-center gap-3 mb-3">
                        <div className="w-9 h-9 bg-[#0A0A0A] text-white flex items-center justify-center text-sm font-display font-bold">
                            {user?.name?.[0]?.toUpperCase()}
                        </div>
                        <div className="min-w-0">
                            <div className="text-sm font-medium truncate" data-testid="current-user-name">{user?.name}</div>
                            <div className="text-xs text-muted-foreground truncate">{roleLabel[user?.role] || user?.role}</div>
                        </div>
                    </div>
                    <button
                        onClick={doLogout}
                        data-testid="logout-btn"
                        className="w-full flex items-center justify-center gap-2 text-xs uppercase tracking-[0.18em] py-2 border border-border hover:bg-[#0A0A0A] hover:text-white transition-colors"
                    >
                        <LogOut className="w-3.5 h-3.5" strokeWidth={2} />
                        Sign out
                    </button>
                </div>
            </aside>

            <main className="flex-1 overflow-auto" data-testid="main-content">
                <Outlet />
            </main>
        </div>
    );
}
