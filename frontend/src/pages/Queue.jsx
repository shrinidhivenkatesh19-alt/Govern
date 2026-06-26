import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useLiveData } from "@/lib/useLiveData";
import { Inbox, AlertTriangle, Clock, RefreshCw } from "lucide-react";

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

const tierColor = (t) =>
    ({ auto_approve: "#16A34A", product_only: "#002FA7", ceo_required: "#FF2400" }[t] || "#0A0A0A");

const filters = [
    { value: "all", label: "All" },
    { value: "pending_acceptance", label: "Awaiting Accept" },
    { value: "in_progress", label: "In Progress" },
    { value: "escalated", label: "Escalated" },
    { value: "approved", label: "Approved" },
    { value: "live", label: "Live" },
];

export default function Queue() {
    const [items, setItems] = useState([]);
    const [filter, setFilter] = useState("all");
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);

    const load = useCallback(async (f) => {
        setLoading(true);
        try {
            const params = f && f !== "all" ? { status_filter: f } : {};
            const r = await api.get("/submissions", { params });
            setItems(r.data);
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Failed to load queue");
            setItems([]);
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, []);

    useLiveData(
        () => {
            setRefreshing(true);
            return load(filter);
        },
        { activePath: "/app/queue", pollMs: 15000 },
    );

    return (
        <div className="p-8 lg:p-10" data-testid="queue-page">
            <div className="mb-8 flex items-start justify-between gap-4">
                <div>
                <div className="label-overline mb-2">Workflow tracker</div>
                <h1 className="font-display text-4xl font-bold tracking-tight">Approval queue.</h1>
                <p className="text-muted-foreground mt-2">Every piece in flight. Status, owner, idle time, deadline.</p>
                </div>
                <button
                    type="button"
                    onClick={() => {
                        setRefreshing(true);
                        load(filter);
                    }}
                    disabled={refreshing}
                    data-testid="queue-refresh-btn"
                    className="inline-flex items-center gap-2 px-3 py-2 border border-border text-xs uppercase tracking-[0.18em] hover:bg-[#F3F4F6] disabled:opacity-60"
                >
                    <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
                    Refresh
                </button>
            </div>

            <div className="flex gap-2 mb-6" data-testid="queue-filters">
                {filters.map((f) => (
                    <button
                        key={f.value}
                        onClick={() => {
                            setFilter(f.value);
                            setRefreshing(true);
                            load(f.value);
                        }}
                        data-testid={`filter-${f.value}`}
                        className={`px-4 py-2 text-xs uppercase tracking-[0.18em] border transition-colors ${
                            filter === f.value
                                ? "bg-[#0A0A0A] text-white border-[#0A0A0A]"
                                : "border-border hover:bg-[#F3F4F6]"
                        }`}
                    >
                        {f.label}
                    </button>
                ))}
            </div>

            <div className="border border-border" data-testid="queue-table-wrapper">
                {loading ? (
                    <div className="p-12 text-center text-muted-foreground text-sm">Loading...</div>
                ) : items.length === 0 ? (
                    <div className="p-16 text-center">
                        <Inbox className="w-10 h-10 mx-auto text-muted-foreground mb-3" />
                        <p className="text-sm text-muted-foreground">No submissions in this view.</p>
                    </div>
                ) : (
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-border bg-[#F3F4F6]">
                                <th className="text-left px-6 py-3 label-overline">Title / Request</th>
                                <th className="text-left px-6 py-3 label-overline">Stuck with</th>
                                <th className="text-left px-6 py-3 label-overline">Status</th>
                                <th className="text-left px-6 py-3 label-overline">Submitter</th>
                                <th className="text-left px-6 py-3 label-overline">Idle</th>
                                <th className="text-left px-6 py-3 label-overline">Deadline</th>
                                <th className="text-left px-6 py-3 label-overline"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {items.map((it) => (
                                <tr
                                    key={it.id}
                                    className="border-b border-border last:border-b-0 hover:bg-[#F3F4F6] transition-colors"
                                    data-testid={`queue-row-${it.id}`}
                                >
                                    <td className="px-6 py-3">
                                        <div className="font-medium flex items-center gap-2">
                                            {it.needs_escalation && <AlertTriangle className="w-3.5 h-3.5 text-[#FF2400]" />}
                                            {it.needs_nudge && !it.needs_escalation && <Clock className="w-3.5 h-3.5 text-[#FFD700]" />}
                                            {it.title}
                                        </div>
                                        <div className="text-xs text-muted-foreground mt-0.5 truncate max-w-xs">
                                            {it.request_type || it.content_type?.replace?.(/_/g, " ") || ""}
                                        </div>
                                    </td>
                                    <td className="px-6 py-3" data-testid={`assignee-${it.id}`}>
                                        {it.assigned_user_name ? (
                                            <>
                                                <div className="font-medium">{it.assigned_user_name}</div>
                                                <div className="text-xs text-muted-foreground">
                                                    {it.assigned_user_designation || it.reviewer_role?.replace?.(/_/g, " ")}
                                                </div>
                                            </>
                                        ) : (
                                            <span className="text-xs text-muted-foreground italic">
                                                {it.reviewer_role?.replace?.(/_/g, " ") || "—"}
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-3">
                                        <span className={`px-2 py-1 text-xs font-medium uppercase tracking-wider ${statusColor(it.status)}`}>
                                            {statusLabels[it.status]}
                                        </span>
                                    </td>
                                    <td className="px-6 py-3 text-muted-foreground">{it.submitter_name}</td>
                                    <td className="px-6 py-3 font-mono text-xs">
                                        {it.idle_hours >= 72 ? (
                                            <span className="text-[#FF2400]">{it.idle_hours}h</span>
                                        ) : it.idle_hours >= 48 ? (
                                            <span className="text-[#B8860B]">{it.idle_hours}h</span>
                                        ) : (
                                            `${it.idle_hours}h`
                                        )}
                                    </td>
                                    <td className="px-6 py-3 text-muted-foreground font-mono text-xs">{it.deadline}</td>
                                    <td className="px-6 py-3 text-right">
                                        <Link
                                            to={`/app/submission/${it.id}`}
                                            className="text-xs underline hover:text-[#002FA7]"
                                            data-testid={`open-${it.id}`}
                                        >
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
