import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { AlertTriangle, Clock, CheckCircle2, ArrowRight, Activity } from "lucide-react";

const statusLabels = {
    scored: "Scored",
    under_review: "Under Review",
    approved: "Approved",
    revision_requested: "Revision",
    escalated: "Escalated",
    live: "Live",
};

const statusColor = (s) =>
    ({
        scored: "bg-[#F3F4F6] text-[#0A0A0A]",
        under_review: "bg-[#002FA7] text-white",
        approved: "bg-[#16A34A] text-white",
        revision_requested: "bg-[#FFD700] text-[#0A0A0A]",
        escalated: "bg-[#FF2400] text-white",
        live: "bg-[#0A0A0A] text-white",
    }[s] || "bg-[#F3F4F6]");

export default function Overview() {
    const { user } = useAuth();
    const [stats, setStats] = useState(null);
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        (async () => {
            const [a, s] = await Promise.all([api.get("/analytics/overview"), api.get("/submissions")]);
            setStats(a.data);
            setItems(s.data);
            setLoading(false);
        })();
    }, []);

    const nudges = items.filter((i) => i.needs_nudge && !i.needs_escalation);
    const escalations = items.filter((i) => i.needs_escalation);
    const recent = items.slice(0, 5);

    return (
        <div className="p-8 lg:p-10" data-testid="overview-page">
            <div className="mb-10">
                <div className="label-overline mb-2">Welcome back, {user?.name}</div>
                <h1 className="font-display text-4xl lg:text-5xl font-bold tracking-tight">Control Room.</h1>
                <p className="text-muted-foreground mt-2 max-w-2xl">
                    Live status of every piece of content in the approval chain. Routine routes itself. The CEO only sees what reaches the CEO desk.
                </p>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-4 border border-border mb-10">
                <KPI label="In Pipeline" value={stats?.total ?? "—"} testid="kpi-total" />
                <KPI label="Awaiting Review" value={stats?.by_status?.under_review ?? 0} accent="#002FA7" testid="kpi-under-review" />
                <KPI label="Escalated" value={stats?.by_status?.escalated ?? 0} accent="#FF2400" testid="kpi-escalated" />
                <KPI label="Avg Approval (hrs)" value={stats?.avg_approval_hours ?? 0} testid="kpi-avg-hours" />
            </div>

            {(nudges.length > 0 || escalations.length > 0) && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-10">
                    {escalations.length > 0 && (
                        <AlertBox
                            color="#FF2400"
                            icon={AlertTriangle}
                            title={`${escalations.length} item${escalations.length > 1 ? "s" : ""} past 72h`}
                            items={escalations.slice(0, 3)}
                            testid="alert-escalations"
                        />
                    )}
                    {nudges.length > 0 && (
                        <AlertBox
                            color="#FFD700"
                            textColor="#0A0A0A"
                            icon={Clock}
                            title={`${nudges.length} item${nudges.length > 1 ? "s" : ""} past 48h — needs nudge`}
                            items={nudges.slice(0, 3)}
                            testid="alert-nudges"
                        />
                    )}
                </div>
            )}

            <div className="border border-border" data-testid="recent-submissions">
                <div className="flex items-center justify-between px-6 py-4 border-b border-border">
                    <div>
                        <div className="label-overline">Recent submissions</div>
                        <h3 className="font-display text-xl font-bold tracking-tight mt-1">Latest activity</h3>
                    </div>
                    <Link to="/app/queue" className="text-sm flex items-center gap-1 hover:text-[#002FA7]" data-testid="view-all-link">
                        View all <ArrowRight className="w-4 h-4" />
                    </Link>
                </div>

                {loading ? (
                    <div className="p-8 text-center text-muted-foreground text-sm">Loading...</div>
                ) : recent.length === 0 ? (
                    <div className="p-12 text-center">
                        <Activity className="w-8 h-8 mx-auto text-muted-foreground mb-3" />
                        <p className="text-sm text-muted-foreground mb-4">No submissions yet.</p>
                        <Link
                            to="/app/submit"
                            className="inline-flex items-center gap-2 px-4 py-2 bg-[#0A0A0A] text-white text-xs uppercase tracking-[0.18em]"
                            data-testid="empty-submit-cta"
                        >
                            Submit first piece <ArrowRight className="w-3 h-3" />
                        </Link>
                    </div>
                ) : (
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-border bg-[#F3F4F6]">
                                <th className="text-left px-6 py-3 label-overline">Title</th>
                                <th className="text-left px-6 py-3 label-overline">Type</th>
                                <th className="text-left px-6 py-3 label-overline">Status</th>
                                <th className="text-left px-6 py-3 label-overline">Idle</th>
                                <th className="text-left px-6 py-3 label-overline"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {recent.map((it) => (
                                <tr key={it.id} className="border-b border-border last:border-b-0 hover:bg-[#F3F4F6] transition-colors" data-testid={`recent-row-${it.id}`}>
                                    <td className="px-6 py-3 font-medium">{it.title}</td>
                                    <td className="px-6 py-3 text-muted-foreground text-xs uppercase tracking-wider">{it.content_type.replace(/_/g, " ")}</td>
                                    <td className="px-6 py-3">
                                        <span className={`px-2 py-1 text-xs font-medium uppercase tracking-wider ${statusColor(it.status)}`}>
                                            {statusLabels[it.status]}
                                        </span>
                                    </td>
                                    <td className="px-6 py-3 font-mono text-xs">{it.idle_hours}h</td>
                                    <td className="px-6 py-3 text-right">
                                        <Link to={`/app/submission/${it.id}`} className="text-xs underline hover:text-[#002FA7]">
                                            Open
                                        </Link>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}

function KPI({ label, value, accent, testid }) {
    return (
        <div className="px-6 py-5 border-r border-b border-border last:border-r-0" data-testid={testid}>
            <div className="label-overline mb-2">{label}</div>
            <div className="font-display text-4xl font-bold tracking-tight" style={{ color: accent || "#0A0A0A" }}>
                {value}
            </div>
        </div>
    );
}

function AlertBox({ color, textColor = "#FFFFFF", icon: Icon, title, items, testid }) {
    return (
        <div className="border" style={{ borderColor: color }} data-testid={testid}>
            <div className="flex items-center gap-2 px-5 py-3" style={{ background: color, color: textColor }}>
                <Icon className="w-4 h-4" strokeWidth={2.25} />
                <span className="font-display font-bold tracking-tight">{title}</span>
            </div>
            <div className="divide-y divide-border">
                {items.map((it) => (
                    <Link
                        key={it.id}
                        to={`/app/submission/${it.id}`}
                        className="flex justify-between items-center px-5 py-3 hover:bg-[#F3F4F6] text-sm"
                    >
                        <span className="truncate pr-3">{it.title}</span>
                        <span className="font-mono text-xs text-muted-foreground whitespace-nowrap">{it.idle_hours}h idle</span>
                    </Link>
                ))}
            </div>
        </div>
    );
}
