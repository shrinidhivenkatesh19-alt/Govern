import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { LayoutDashboard, FilePlus2, Inbox, BarChart3, LogOut, ShieldCheck, Menu } from "lucide-react";
import NotificationBell from "@/components/NotificationBell";
import ThemeToggle from "@/components/ThemeToggle";

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
    vp: "Vice President",
    ceo: "CEO",
};

export default function Shell() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const [collapsed, setCollapsed] = useState(() => localStorage.getItem("caa_sidebar_collapsed") === "true");

    const canViewGovernance = ["vp", "ceo"].includes(user?.role);
    const visibleNav = navItems.filter((n) => n.to !== "/app/analytics" || canViewGovernance);

    const doLogout = () => {
        logout();
        navigate("/login");
    };

    const toggleSidebar = () => {
        setCollapsed((c) => {
            localStorage.setItem("caa_sidebar_collapsed", String(!c));
            return !c;
        });
    };

    return (
        <div className="min-h-screen flex bg-background" data-testid="app-shell">
            <aside
                className={`border-r border-border bg-background flex flex-col transition-all duration-200 ${
                    collapsed ? "w-16" : "w-64"
                }`}
                data-testid="sidebar"
            >
                <div className={`border-b border-border flex items-center justify-start px-4 py-4`}>
                    <button
                        onClick={toggleSidebar}
                        data-testid="sidebar-toggle-btn"
                        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                        className="w-9 h-9 flex items-center justify-center hover:bg-[#F3F4F6] dark:hover:bg-white/10 transition-colors"
                    >
                        <Menu className="w-4.5 h-4.5" strokeWidth={1.75} />
                    </button>
                </div>

                <nav className="flex-1 py-4">
                    {visibleNav.map((item) => (
                        <NavLink
                            key={item.to}
                            to={item.to}
                            end={item.end}
                            data-testid={item.testid}
                            title={collapsed ? item.label : undefined}
                            className={({ isActive }) =>
                                `flex items-center gap-3 text-sm border-l-2 transition-colors ${
                                    collapsed ? "justify-center px-0 py-3" : "px-6 py-3"
                                } ${
                                    isActive
                                        ? "border-[#002FA7] bg-[#F3F4F6] dark:bg-white/10 text-foreground font-medium"
                                        : "border-transparent text-muted-foreground hover:bg-[#F3F4F6] dark:hover:bg-white/10 hover:text-foreground"
                                }`
                            }
                        >
                            <item.icon className="w-4 h-4 shrink-0" strokeWidth={1.75} />
                            {!collapsed && item.label}
                        </NavLink>
                    ))}
                </nav>

                <div className={`border-t border-border ${collapsed ? "p-2" : "p-4"}`}>
                    <div className={`flex items-center mb-3 ${collapsed ? "justify-center" : "gap-3"}`}>
                        <div
                            className="w-9 h-9 bg-[#0A0A0A] text-white flex items-center justify-center text-sm font-display font-bold shrink-0"
                            title={collapsed ? user?.name : undefined}
                        >
                            {user?.name?.[0]?.toUpperCase()}
                        </div>
                        {!collapsed && (
                            <div className="min-w-0">
                                <div className="text-sm font-medium truncate" data-testid="current-user-name">{user?.name}</div>
                                <div className="text-xs text-muted-foreground truncate">{roleLabel[user?.role] || user?.role}</div>
                            </div>
                        )}
                    </div>
                    <button
                        onClick={doLogout}
                        data-testid="logout-btn"
                        title={collapsed ? "Sign out" : undefined}
                        className="w-full flex items-center justify-center gap-2 text-xs uppercase tracking-[0.18em] py-2 border border-border hover:bg-[#0A0A0A] hover:text-white transition-colors"
                    >
                        <LogOut className="w-3.5 h-3.5 shrink-0" strokeWidth={2} />
                        {!collapsed && "Sign out"}
                    </button>
                </div>
            </aside>

            <main className="flex-1 overflow-auto" data-testid="main-content">
                <div
                    className="flex items-center justify-between px-6 py-3 border-b border-border bg-background sticky top-0 z-40"
                    data-testid="topbar"
                >
                    <button
                        onClick={() => navigate("/app")}
                        data-testid="home-logo-btn"
                        aria-label="Go to homepage"
                        className="flex items-center gap-2 hover:opacity-70 transition-opacity"
                    >
                        <div className="w-7 h-7 bg-[#0A0A0A] flex items-center justify-center">
                            <ShieldCheck className="w-4 h-4 text-white" strokeWidth={2} />
                        </div>
                        <div className="text-left">
                            <div className="font-display font-bold text-base leading-none tracking-tight">GOVERN</div>
                            <div className="label-overline mt-1 text-[10px]">Approval Agent</div>
                        </div>
                    </button>

                    <div className="flex items-center gap-2">
                        <NotificationBell />
                        <ThemeToggle />
                    </div>
                </div>
                <Outlet />
            </main>
        </div>
    );
}