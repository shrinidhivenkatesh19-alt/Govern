import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { useLiveData, notifyDataChanged } from "@/lib/useLiveData";
import { AlertTriangle, Clock, ArrowRight, Activity, Bell, Loader2, GitBranch, RefreshCw } from "lucide-react";

const statusLabels = {
    scored: "Scored",
    pending_acceptance: "Awaiting Accept",
    in_progress: "In Progress",
    under_review: "Under Review",
    approved: "Approved",
    revision_requested: "Revision",
    escalated: "Escalated",
    live: "Live",
};

const statusColor = (s) =>
    ({
        scored: "bg-[#F3F4F6] text-[#0A0A0A]",
        pending_acceptance: "bg-[#FFD700] text-[#0A0A0A]",
        in_progress: "bg-[#002FA7] text-white",
        under_review: "bg-[#002FA7] text-white",
        approved: "bg-[#16A34A] text-white",
        revision_requested: "bg-[#FFD700] text-[#0A0A0A]",
        escalated: "bg-[#FF2400] text-white",
        live: "bg-[#0A0A0A] text-white",
    }[s] || "bg-[#F3F4F6]");

// Pick the SLA date that is currently being raced
const currentSlaTarget = (it) => {
    const tl = it.timeline || {};
    if (it.status === "pending_acceptance") return { label: "Accept by", date: tl.accept_by, breached: it.timeline_overdue?.accept };
    if (it.status === "in_progress") return { label: "Review by", date: tl.review_by, breached: it.timeline_overdue?.review };
    if (it.status === "under_review" || it.status === "escalated") return { label: "Approve by", date: tl.approve_by, breached: it.timeline_overdue?.approve };
    return { label: "Deadline", date: it.deadline };
};

export default function Overview() {
    const { user } = useAuth();
    const [stats, setStats] = useState(null);
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [bulkNudging, setBulkNudging] = useState(false);
    const [rowNudging, setRowNudging] = useState({});

    const [refreshing, setRefreshing] = useState(false);

    const load = useCallback(async () => {
        try {
            const [a, s] = await Promise.all([api.get("/dashboard/stats"), api.get("/submissions")]);
            setStats(a.data);
            setItems(s.data);
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Failed to load dashboard");
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, []);

    useLiveData(
        () => {
            setRefreshing(true);
            return load();
        },
        { activePath: "/app", exact: true, pollMs: 15000 },
    );

    const nudges = items.filter((i) => i.needs_nudge && !i.needs_escalation);
    const escalations = items.filter((i) => i.needs_escalation);
    const recent = items.slice(0, 5);

    const bulkNudge = async (ids) => {
        if (!ids.length) return;
        setBulkNudging(true);
        try {
            const r = await api.post("/submissions/bulk-nudge", {
                submission_ids: ids,
                note: "Bulk nudge from Control Room",
            });
            const ok = r.data.nudged;
            const failed = r.data.failed?.length || 0;
            if (failed === 0) toast.success(`Nudged ${ok} reviewer${ok === 1 ? "" : "s"}`);
            else toast.warning(`Nudged ${ok}, ${failed} skipped`);
            notifyDataChanged();
            await load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Bulk nudge failed");
        } finally {
            setBulkNudging(false);
        }
    };

    const nudgeOne = async (id) => {
        setRowNudging((s) => ({ ...s, [id]: true }));
        try {
            await api.post(`/submissions/${id}/nudge`, { note: "Nudge from Control Room" });
            toast.success("Reviewer nudged");
            notifyDataChanged();
            await load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Nudge failed");
        } finally {
            setRowNudging((s) => ({ ...s, [id]: false }));
        }
    };

    return (
        <div className="p-8 lg:p-10" data-testid="overview-page">
            <div className="mb-10 flex items-start justify-between gap-4">
                <div>
                <div className="label-overline mb-2">Welcome back, {user?.name}</div>
                <h1 className="font-display text-4xl lg:text-5xl font-bold tracking-tight">Control Room.</h1>
                <p className="text-muted-foreground mt-2 max-w-2xl">
                    Live status of every piece of content in the approval chain. Routine routes itself. The CEO only sees what reaches the CEO desk.
                </p>
                </div>
                <button
                    type="button"
                    onClick={() => {
                        setRefreshing(true);
                        load();
                    }}
                    disabled={refreshing}
                    data-testid="overview-refresh-btn"
                    className="inline-flex items-center gap-2 px-3 py-2 border border-border text-xs uppercase tracking-[0.18em] hover:bg-[#F3F4F6] disabled:opacity-60"
                >
                    <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
                    Refresh
                </button>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-4 border border-border mb-10">
                <KPI label="In Pipeline" value={stats?.total ?? "—"} testid="kpi-total" />
                <KPI label="Awaiting Accept" value={stats?.by_status?.pending_acceptance ?? 0} accent="#FFD700" testid="kpi-pending" />
                <KPI label="Escalated" value={stats?.by_status?.escalated ?? 0} accent="#FF2400" testid="kpi-escalated" />
                <KPI label="Avg Approval (hrs)" value={stats?.avg_approval_hours ?? 0} testid="kpi-avg-hours" />
            </div>

            {escalations.length > 0 && (
                <EscalationAlert items={escalations.slice(0, 5)} />
            )}

            {nudges.length > 0 && (
                <NudgeTable
                    items={nudges}
                    onNudgeOne={nudgeOne}
                    onBulkNudge={() => bulkNudge(nudges.map((n) => n.id))}
                    bulkBusy={bulkNudging}
                    rowBusy={rowNudging}
                />
            )}

            <div className="border border-border mt-10" data-testid="recent-submissions">
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
                                <th className="text-left px-6 py-3 label-overline">Stuck with</th>
                                <th className="text-left px-6 py-3 label-overline">Status</th>
                                <th className="text-left px-6 py-3 label-overline">Step idle</th>
                                <th className="text-left px-6 py-3 label-overline"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {recent.map((it) => {
                                const stepNum = (it.approval_chain?.length || 0) + 1;
                                return (
                                    <tr key={it.id} className="border-b border-border last:border-b-0 hover:bg-[#F3F4F6] transition-colors" data-testid={`recent-row-${it.id}`}>
                                        <td className="px-6 py-3 font-medium">{it.title}</td>
                                        <td className="px-6 py-3">
                                            {it.assigned_user_name ? (
                                                <>
                                                    <div className="font-medium text-xs">{it.assigned_user_name}</div>
                                                    <div className="text-[10px] text-muted-foreground">
                                                        {it.assigned_user_designation || it.reviewer_role?.replace?.(/_/g, " ")}
                                                    </div>
                                                </>
                                            ) : (
                                                <span className="text-xs text-muted-foreground">—</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-3">
                                            <span className={`px-2 py-1 text-xs font-medium uppercase tracking-wider ${statusColor(it.status)}`}>
                                                {statusLabels[it.status]}
                                            </span>
                                        </td>
                                        <td className="px-6 py-3">
                                            <div className="font-mono text-xs">{it.idle_hours}h</div>
                                            <div className="text-[10px] text-muted-foreground flex items-center gap-1 mt-0.5">
                                                <GitBranch className="w-2.5 h-2.5" /> step {stepNum}
                                            </div>
                                        </td>
                                        <td className="px-6 py-3 text-right">
                                            <Link to={`/app/submission/${it.id}`} className="text-xs underline hover:text-[#002FA7]" data-testid={`open-${it.id}`}>
                                                Open
                                            </Link>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}

function NudgeTable({ items, onNudgeOne, onBulkNudge, bulkBusy, rowBusy }) {
    return (
        <div className="border border-[#FFD700] mb-10" data-testid="nudge-table">
            <div className="flex items-center justify-between gap-3 px-5 py-3 bg-[#FFD700] text-[#0A0A0A]">
                <div className="flex items-center gap-2 min-w-0">
                    <Clock className="w-4 h-4 shrink-0" strokeWidth={2.25} />
                    <span className="font-display font-bold tracking-tight">
                        {items.length} item{items.length > 1 ? "s" : ""} past 48h — needs nudge
                    </span>
                </div>
                <button
                    onClick={onBulkNudge}
                    disabled={bulkBusy}
                    data-testid="nudge-all-btn"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#0A0A0A] text-white text-[10px] uppercase tracking-[0.18em] hover:bg-[#002FA7] transition-colors disabled:opacity-60"
                >
                    {bulkBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Bell className="w-3 h-3" />}
                    {bulkBusy ? "Nudging..." : `Nudge all (${items.length})`}
                </button>
            </div>

            <table className="w-full text-sm">
                <thead>
                    <tr className="border-b border-border bg-white">
                        <th className="text-left px-5 py-2.5 label-overline">Title</th>
                        <th className="text-left px-5 py-2.5 label-overline">Stuck with</th>
                        <th className="text-left px-5 py-2.5 label-overline">Step idle</th>
                        <th className="text-left px-5 py-2.5 label-overline">Current SLA</th>
                        <th className="text-right px-5 py-2.5 label-overline">Action</th>
                    </tr>
                </thead>
                <tbody>
                    {items.map((it) => {
                        const sla = currentSlaTarget(it);
                        const stepNum = (it.approval_chain?.length || 0) + 1;
                        const busy = !!rowBusy[it.id];
                        return (
                            <tr key={it.id} className="border-b border-border last:border-b-0 hover:bg-[#FFFEF7] transition-colors" data-testid={`nudge-row-${it.id}`}>
                                <td className="px-5 py-2.5">
                                    <Link to={`/app/submission/${it.id}`} className="font-medium hover:text-[#002FA7]">
                                        {it.title}
                                    </Link>
                                </td>
                                <td className="px-5 py-2.5">
                                    {it.assigned_user_name ? (
                                        <>
                                            <div className="font-medium text-xs">{it.assigned_user_name}</div>
                                            <div className="text-[10px] text-muted-foreground">
                                                {it.assigned_user_designation || it.reviewer_role?.replace?.(/_/g, " ")}
                                            </div>
                                        </>
                                    ) : (
                                        <span className="text-xs text-muted-foreground">—</span>
                                    )}
                                </td>
                                <td className="px-5 py-2.5">
                                    <div className={`font-mono text-xs ${it.idle_hours >= 72 ? "text-[#FF2400] font-bold" : ""}`}>
                                        {it.idle_hours}h
                                    </div>
                                    <div className="text-[10px] text-muted-foreground flex items-center gap-1 mt-0.5">
                                        <GitBranch className="w-2.5 h-2.5" /> step {stepNum}
                                    </div>
                                </td>
                                <td className="px-5 py-2.5">
                                    <div className="text-[10px] label-overline">{sla.label}</div>
                                    <div className={`font-mono text-xs ${sla.breached ? "text-[#FF2400] font-bold" : ""}`}>
                                        {sla.date || "—"}
                                        {sla.breached && <span className="ml-1 text-[9px] uppercase tracking-wider">breached</span>}
                                    </div>
                                </td>
                                <td className="px-5 py-2.5 text-right whitespace-nowrap">
                                    <button
                                        onClick={() => onNudgeOne(it.id)}
                                        disabled={busy}
                                        data-testid={`row-nudge-${it.id}`}
                                        title="Nudge assigned reviewer"
                                        className="inline-flex items-center gap-1 px-2.5 py-1.5 bg-[#0A0A0A] text-white text-[10px] uppercase tracking-[0.18em] hover:bg-[#002FA7] disabled:opacity-60"
                                    >
                                        {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Bell className="w-3 h-3" />}
                                        {busy ? "..." : "Nudge"}
                                    </button>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

function EscalationAlert({ items }) {
    return (
        <div className="border border-[#FF2400] mb-10" data-testid="alert-escalations">
            <div className="flex items-center gap-2 px-5 py-3 bg-[#FF2400] text-white">
                <AlertTriangle className="w-4 h-4" strokeWidth={2.25} />
                <span className="font-display font-bold tracking-tight">
                    {items.length} item{items.length > 1 ? "s" : ""} past 72h
                </span>
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

function KPI({ label, value, accent, testid }) {
    return (
        <div className="px-6 py-5 border-r border-b border-border last:border-r-0" data-testid={testid}>
            <div className="label-overline mb-2">{label}</div>
            <div className="font-display text-4xl font-bold tracking-tight" style={{ color: accent || "hsl(var(--foreground))" }}>
                {value}
            </div>
        </div>
    );
}
