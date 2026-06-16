import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import AIScoringPanel from "@/components/AIScoringPanel";
import { CheckCircle2, AlertTriangle, ArrowUp, Bell, Send, ArrowLeft, Clock } from "lucide-react";

const statusLabels = {
    scored: "Scored",
    under_review: "Under Review",
    approved: "Approved",
    revision_requested: "Revision Requested",
    escalated: "Escalated to CEO",
    live: "Live",
};

const statusBg = {
    scored: "#F3F4F6",
    under_review: "#002FA7",
    approved: "#16A34A",
    revision_requested: "#FFD700",
    escalated: "#FF2400",
    live: "#0A0A0A",
};

export default function SubmissionDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const [item, setItem] = useState(null);
    const [loading, setLoading] = useState(true);
    const [note, setNote] = useState("");
    const [acting, setActing] = useState(false);

    const load = async () => {
        try {
            const r = await api.get(`/submissions/${id}`);
            setItem(r.data);
        } catch {
            toast.error("Submission not found");
            navigate("/app/queue");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load();
    }, [id]);

    const act = async (endpoint, requireNote = false) => {
        if (requireNote && !note.trim()) {
            toast.error("Note required for this action");
            return;
        }
        setActing(true);
        try {
            await api.post(`/submissions/${id}/${endpoint}`, { note });
            setNote("");
            toast.success("Action recorded");
            await load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Action failed");
        } finally {
            setActing(false);
        }
    };

    if (loading) return <div className="p-10 text-sm text-muted-foreground">Loading...</div>;
    if (!item) return null;

    const canApprove = ["reviewer", "marketing_lead", "ceo"].includes(user?.role);
    const canMarkLive = item.status === "approved";
    const isOpen = ["under_review", "escalated", "revision_requested"].includes(item.status);

    const textColor = item.status === "revision_requested" ? "#0A0A0A" : "#FFFFFF";

    return (
        <div className="p-8 lg:p-10 max-w-6xl" data-testid="submission-detail-page">
            <Link to="/app/queue" className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] mb-6 hover:text-[#002FA7]" data-testid="back-to-queue">
                <ArrowLeft className="w-3.5 h-3.5" /> Back to queue
            </Link>

            <div className="flex items-start justify-between gap-6 mb-8">
                <div>
                    <div className="label-overline mb-2">{item.content_type.replace(/_/g, " ")}</div>
                    <h1 className="font-display text-4xl font-bold tracking-tight max-w-2xl">{item.title}</h1>
                    <div className="flex items-center gap-4 mt-3 text-sm text-muted-foreground">
                        <span>By {item.submitter_name}</span>
                        <span>·</span>
                        <span className="font-mono">Deadline {item.deadline}</span>
                        <span>·</span>
                        <span className="inline-flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5" /> {item.idle_hours}h in stage
                        </span>
                    </div>
                </div>

                <span
                    className="px-3 py-1.5 text-xs font-medium uppercase tracking-[0.18em]"
                    style={{ background: statusBg[item.status], color: textColor }}
                    data-testid="status-badge"
                >
                    {statusLabels[item.status]}
                </span>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
                <div className="lg:col-span-3 space-y-6">
                    <Section title="Brief">
                        <p className="whitespace-pre-wrap text-sm leading-relaxed">{item.brief}</p>
                    </Section>

                    <Section title="Content">
                        <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed">{item.content}</pre>
                    </Section>

                    <Section title="Activity">
                        <ol className="space-y-4" data-testid="activity-timeline">
                            {item.activity.map((a, i) => (
                                <li key={i} className="flex gap-4 text-sm">
                                    <div className="w-2 h-2 mt-1.5 bg-[#0A0A0A] rounded-full shrink-0" />
                                    <div className="flex-1 border-l border-border pl-4 -ml-3">
                                        <div className="flex items-baseline justify-between gap-3">
                                            <div className="font-medium">
                                                {a.actor} <span className="text-muted-foreground font-normal">— {a.action.replace(/_/g, " ")}</span>
                                            </div>
                                            <div className="font-mono text-xs text-muted-foreground">{new Date(a.ts).toLocaleString()}</div>
                                        </div>
                                        {a.note && <div className="text-muted-foreground text-sm mt-1">{a.note}</div>}
                                    </div>
                                </li>
                            ))}
                        </ol>
                    </Section>
                </div>

                <div className="lg:col-span-2 space-y-6">
                    <AIScoringPanel result={item.score_result} />

                    {isOpen && canApprove && (
                        <div className="border border-border p-5" data-testid="action-panel">
                            <div className="label-overline mb-2">Reviewer actions</div>
                            <h3 className="font-display font-bold text-lg mb-4 tracking-tight">Move it forward.</h3>

                            <textarea
                                value={note}
                                onChange={(e) => setNote(e.target.value)}
                                placeholder="Optional note (required for revision)..."
                                rows={3}
                                data-testid="action-note"
                                className="w-full px-3 py-2 border border-border focus:outline-none focus:ring-2 focus:ring-[#002FA7] text-sm resize-none mb-3"
                            />

                            <div className="grid grid-cols-1 gap-2">
                                <button
                                    onClick={() => act("approve")}
                                    disabled={acting}
                                    data-testid="approve-btn"
                                    className="flex items-center justify-center gap-2 py-2.5 bg-[#16A34A] text-white hover:bg-[#0A0A0A] uppercase tracking-[0.18em] text-xs font-medium disabled:opacity-60"
                                >
                                    <CheckCircle2 className="w-4 h-4" /> Approve
                                </button>
                                <button
                                    onClick={() => act("request-revision", true)}
                                    disabled={acting}
                                    data-testid="revision-btn"
                                    className="flex items-center justify-center gap-2 py-2.5 bg-[#FFD700] text-[#0A0A0A] hover:bg-[#0A0A0A] hover:text-white uppercase tracking-[0.18em] text-xs font-medium disabled:opacity-60"
                                >
                                    <AlertTriangle className="w-4 h-4" /> Request revision
                                </button>
                                {user?.role !== "ceo" && item.status !== "escalated" && (
                                    <button
                                        onClick={() => act("escalate")}
                                        disabled={acting}
                                        data-testid="escalate-btn"
                                        className="flex items-center justify-center gap-2 py-2.5 bg-[#FF2400] text-white hover:bg-[#0A0A0A] uppercase tracking-[0.18em] text-xs font-medium disabled:opacity-60"
                                    >
                                        <ArrowUp className="w-4 h-4" /> Escalate to CEO
                                    </button>
                                )}
                            </div>
                        </div>
                    )}

                    {isOpen && (
                        <div className="border border-border p-5" data-testid="nudge-block">
                            <div className="label-overline mb-2">Workflow</div>
                            <button
                                onClick={() => act("nudge")}
                                disabled={acting}
                                data-testid="nudge-btn"
                                className="w-full flex items-center justify-center gap-2 py-2.5 border border-border hover:bg-[#0A0A0A] hover:text-white uppercase tracking-[0.18em] text-xs"
                            >
                                <Bell className="w-3.5 h-3.5" /> Nudge reviewer
                            </button>
                            <p className="text-xs text-muted-foreground mt-2">Auto-escalates at 72h idle.</p>
                        </div>
                    )}

                    {canMarkLive && (
                        <button
                            onClick={() => act("mark-live")}
                            disabled={acting}
                            data-testid="mark-live-btn"
                            className="w-full flex items-center justify-center gap-2 py-3 bg-[#0A0A0A] text-white hover:bg-[#002FA7] uppercase tracking-[0.18em] text-xs font-medium"
                        >
                            <Send className="w-4 h-4" /> Mark as live
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}

function Section({ title, children }) {
    return (
        <div className="border border-border">
            <div className="px-5 py-3 border-b border-border bg-[#F3F4F6]">
                <div className="label-overline">{title}</div>
            </div>
            <div className="p-5">{children}</div>
        </div>
    );
}
