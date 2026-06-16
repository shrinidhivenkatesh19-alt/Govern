import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import AIScoringPanel from "@/components/AIScoringPanel";
import TimelineEditor from "@/components/TimelineEditor";
import {
    CheckCircle2,
    AlertTriangle,
    ArrowUp,
    Bell,
    Send,
    ArrowLeft,
    Clock,
    Download,
    FileText,
    Image as ImageIcon,
    FileType,
    Calendar,
    ChevronUp,
    Pencil,
    X,
    ArrowRightCircle,
} from "lucide-react";

const statusLabels = {
    scored: "Scored",
    pending_acceptance: "Awaiting Acceptance",
    in_progress: "In Progress",
    under_review: "Under Review",
    approved: "Approved",
    revision_requested: "Revision Requested",
    escalated: "Escalated",
    live: "Live",
};

const statusBg = {
    scored: "#F3F4F6",
    pending_acceptance: "#FFD700",
    in_progress: "#002FA7",
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
    const [editingTimeline, setEditingTimeline] = useState(false);
    const [proposedTimeline, setProposedTimeline] = useState(null);

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

    const act = async (endpoint, payload = {}, requireNote = false) => {
        if (requireNote && !note.trim()) {
            toast.error("Note required for this action");
            return;
        }
        setActing(true);
        try {
            await api.post(`/submissions/${id}/${endpoint}`, { note, ...payload });
            setNote("");
            toast.success("Action recorded");
            await load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Action failed");
        } finally {
            setActing(false);
        }
    };

    const submitProposal = async () => {
        if (!proposedTimeline) return;
        setActing(true);
        try {
            await api.post(`/submissions/${id}/propose-timeline`, { ...proposedTimeline, note });
            toast.success("Timeline change proposed");
            setEditingTimeline(false);
            setProposedTimeline(null);
            setNote("");
            await load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Proposal failed");
        } finally {
            setActing(false);
        }
    };

    const agreeTimeline = async () => {
        setActing(true);
        try {
            await api.post(`/submissions/${id}/agree-timeline`, { note });
            toast.success("Timeline agreed");
            setNote("");
            await load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Failed");
        } finally {
            setActing(false);
        }
    };

    if (loading) return <div className="p-10 text-sm text-muted-foreground">Loading...</div>;
    if (!item) return null;

    const isSubmitter = user?.id === item.submitter_id;
    const isAssignedReviewer = user?.role === item.reviewer_role;
    const canApprove = ["reviewer", "marketing_lead", "vp", "ceo"].includes(user?.role) && isAssignedReviewer;
    const canAccept = item.status === "pending_acceptance" && isAssignedReviewer;
    const canForwardToCEO = user?.role === "vp" && ["in_progress", "pending_acceptance"].includes(item.status);
    const canMarkLive = item.status === "approved" && (isAssignedReviewer || isSubmitter);
    const isOpen = ["under_review", "escalated", "revision_requested", "in_progress"].includes(item.status);
    const canEscalate = ["reviewer", "marketing_lead"].includes(user?.role) && isAssignedReviewer && isOpen;
    const canProposeTimeline = (isSubmitter || isAssignedReviewer) && !item.pending_timeline_proposal && ["pending_acceptance", "in_progress", "under_review"].includes(item.status);
    const proposal = item.pending_timeline_proposal;
    const otherPartyMustAgree = proposal && user?.id !== proposal.proposed_by && (isSubmitter || isAssignedReviewer);

    const textColor = item.status === "revision_requested" || item.status === "pending_acceptance" ? "#0A0A0A" : "#FFFFFF";

    return (
        <div className="p-8 lg:p-10 max-w-6xl" data-testid="submission-detail-page">
            <Link to="/app/queue" className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] mb-6 hover:text-[#002FA7]" data-testid="back-to-queue">
                <ArrowLeft className="w-3.5 h-3.5" /> Back to queue
            </Link>

            <div className="flex items-start justify-between gap-6 mb-8">
                <div>
                    <div className="label-overline mb-2">
                        {item.content_type.replace(/_/g, " ")} · assigned to {item.reviewer_role.replace(/_/g, " ")}
                    </div>
                    <h1 className="font-display text-4xl font-bold tracking-tight max-w-2xl">{item.title}</h1>
                    <div className="flex flex-wrap items-center gap-4 mt-3 text-sm text-muted-foreground">
                        <span>By {item.submitter_name}</span>
                        <span>·</span>
                        <span className="font-mono">Deadline {item.deadline}</span>
                        <span>·</span>
                        <span className="inline-flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5" /> {item.idle_hours}h in stage
                        </span>
                        {item.deadline_progress >= 0.8 && (
                            <span className="inline-flex items-center gap-1 text-[#FF2400] font-medium">
                                <AlertTriangle className="w-3.5 h-3.5" /> {Math.round(item.deadline_progress * 100)}% of deadline
                            </span>
                        )}
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
                    <TimelineSection
                        item={item}
                        canPropose={canProposeTimeline}
                        editing={editingTimeline}
                        setEditing={setEditingTimeline}
                        proposedTimeline={proposedTimeline}
                        setProposedTimeline={setProposedTimeline}
                        submitProposal={submitProposal}
                        agreeTimeline={agreeTimeline}
                        canAgree={otherPartyMustAgree}
                        acting={acting}
                    />

                    <Section title="Brief">
                        <p className="whitespace-pre-wrap text-sm leading-relaxed">{item.brief}</p>
                    </Section>

                    <Section title="Content">
                        <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed">{item.content}</pre>
                    </Section>

                    {item.attachments?.length > 0 && (
                        <Section title={`Attachments (${item.attachments.length})`}>
                            <ul className="space-y-2" data-testid="attachments-list">
                                {item.attachments.map((a) => {
                                    const ext = a.original_filename.split(".").pop()?.toLowerCase();
                                    const Icon = ["png", "jpg", "jpeg", "gif", "webp"].includes(ext)
                                        ? ImageIcon
                                        : ext === "pdf"
                                        ? FileType
                                        : FileText;
                                    const token = localStorage.getItem("caa_token");
                                    const downloadUrl = `${process.env.REACT_APP_BACKEND_URL}/api/files/${a.id}/download?auth=${token}`;
                                    return (
                                        <li
                                            key={a.id}
                                            className="flex items-center gap-3 px-3 py-2 border border-border"
                                            data-testid={`attachment-${a.id}`}
                                        >
                                            <Icon className="w-4 h-4 text-[#002FA7] shrink-0" strokeWidth={1.75} />
                                            <div className="flex-1 min-w-0">
                                                <a
                                                    href={downloadUrl}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="text-sm font-medium hover:text-[#002FA7] truncate block"
                                                >
                                                    {a.original_filename}
                                                </a>
                                                <div className="text-xs text-muted-foreground font-mono">
                                                    {a.size < 1024
                                                        ? `${a.size} B`
                                                        : a.size < 1024 * 1024
                                                        ? `${Math.round(a.size / 1024)} KB`
                                                        : `${(a.size / 1024 / 1024).toFixed(1)} MB`}
                                                </div>
                                            </div>
                                            <a
                                                href={downloadUrl}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="p-2 hover:bg-[#0A0A0A] hover:text-white transition-colors"
                                            >
                                                <Download className="w-3.5 h-3.5" />
                                            </a>
                                        </li>
                                    );
                                })}
                            </ul>
                        </Section>
                    )}

                    <Section title="Activity">
                        <ol className="space-y-4" data-testid="activity-timeline">
                            {item.activity.map((a, i) => (
                                <li key={i} className="flex gap-4 text-sm">
                                    <div
                                        className={`w-2 h-2 mt-1.5 rounded-full shrink-0 ${
                                            a.actor_role === "system" ? "bg-[#FFD700]" : "bg-[#0A0A0A]"
                                        }`}
                                    />
                                    <div className="flex-1 border-l border-border pl-4 -ml-3">
                                        <div className="flex items-baseline justify-between gap-3">
                                            <div className="font-medium">
                                                {a.actor}{" "}
                                                <span className="text-muted-foreground font-normal">
                                                    — {a.action.replace(/_/g, " ")}
                                                </span>
                                            </div>
                                            <div className="font-mono text-xs text-muted-foreground">
                                                {new Date(a.ts).toLocaleString()}
                                            </div>
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

                    {canAccept && (
                        <div className="border border-border p-5" data-testid="accept-panel">
                            <div className="label-overline mb-2">Awaiting your acceptance</div>
                            <h3 className="font-display font-bold text-lg mb-3 tracking-tight">Accept this assignment?</h3>
                            <p className="text-xs text-muted-foreground mb-4">
                                Accepting moves the submission to "In Progress". You can propose a revised timeline in the timeline panel above first.
                            </p>
                            <button
                                onClick={() => act("accept")}
                                disabled={acting}
                                data-testid="accept-btn"
                                className="w-full flex items-center justify-center gap-2 py-2.5 bg-[#002FA7] text-white hover:bg-[#0A0A0A] uppercase tracking-[0.18em] text-xs font-medium disabled:opacity-60"
                            >
                                <CheckCircle2 className="w-4 h-4" /> Accept assignment
                            </button>
                        </div>
                    )}

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
                                    onClick={() => act("request-revision", {}, true)}
                                    disabled={acting}
                                    data-testid="revision-btn"
                                    className="flex items-center justify-center gap-2 py-2.5 bg-[#FFD700] text-[#0A0A0A] hover:bg-[#0A0A0A] hover:text-white uppercase tracking-[0.18em] text-xs font-medium disabled:opacity-60"
                                >
                                    <AlertTriangle className="w-4 h-4" /> Request revision
                                </button>
                                {canEscalate && (
                                    <button
                                        onClick={() => act("escalate")}
                                        disabled={acting}
                                        data-testid="escalate-btn"
                                        className="flex items-center justify-center gap-2 py-2.5 bg-[#FF2400] text-white hover:bg-[#0A0A0A] uppercase tracking-[0.18em] text-xs font-medium disabled:opacity-60"
                                    >
                                        <ArrowUp className="w-4 h-4" /> Escalate one level up
                                    </button>
                                )}
                                {canForwardToCEO && (
                                    <button
                                        onClick={() => act("forward-to-ceo")}
                                        disabled={acting}
                                        data-testid="forward-ceo-btn"
                                        className="flex items-center justify-center gap-2 py-2.5 bg-[#FF2400] text-white hover:bg-[#0A0A0A] uppercase tracking-[0.18em] text-xs font-medium disabled:opacity-60"
                                    >
                                        <ArrowRightCircle className="w-4 h-4" /> Forward to CEO
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
                            <p className="text-xs text-muted-foreground mt-2">
                                Auto-nudges fire when timeline SLAs are breached. Hard escalation at 80% of deadline progress.
                            </p>
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

function TimelineSection({ item, canPropose, editing, setEditing, proposedTimeline, setProposedTimeline, submitProposal, agreeTimeline, canAgree, acting }) {
    const tl = item.timeline;
    const overdue = item.timeline_overdue || {};
    const proposal = item.pending_timeline_proposal;

    const startEdit = () => {
        setProposedTimeline({ ...tl });
        setEditing(true);
    };

    return (
        <div className="border border-border" data-testid="timeline-section">
            <div className="flex items-center justify-between px-5 py-3 border-b border-border bg-[#F3F4F6]">
                <div>
                    <div className="label-overline">Timeline</div>
                    <div className="text-xs text-muted-foreground mt-1">
                        {item.timeline_agreed ? "Agreed" : "Proposed by submitter — awaiting acceptance"}
                    </div>
                </div>
                {canPropose && !editing && (
                    <button
                        onClick={startEdit}
                        data-testid="propose-timeline-btn"
                        className="text-xs flex items-center gap-1 hover:text-[#002FA7]"
                    >
                        <Pencil className="w-3 h-3" /> Propose change
                    </button>
                )}
            </div>

            {!editing && (
                <div className="grid grid-cols-3 divide-x divide-border">
                    <TimelineCell label="Accept by" value={tl?.accept_by} overdue={overdue.accept} testid="tl-accept" />
                    <TimelineCell label="Review by" value={tl?.review_by} overdue={overdue.review} testid="tl-review" />
                    <TimelineCell label="Approve by" value={tl?.approve_by} overdue={overdue.approve} testid="tl-approve" />
                </div>
            )}

            {editing && (
                <div className="p-5 space-y-4" data-testid="timeline-editor-wrapper">
                    <TimelineEditor value={proposedTimeline} onChange={setProposedTimeline} />
                    <div className="flex gap-2">
                        <button
                            onClick={submitProposal}
                            disabled={acting}
                            data-testid="submit-proposal-btn"
                            className="px-4 py-2 bg-[#002FA7] text-white text-xs uppercase tracking-[0.18em] hover:bg-[#0A0A0A]"
                        >
                            Send proposal
                        </button>
                        <button
                            onClick={() => setEditing(false)}
                            className="px-4 py-2 border border-border text-xs uppercase tracking-[0.18em] hover:bg-[#F3F4F6]"
                        >
                            <X className="w-3.5 h-3.5 inline mr-1" /> Cancel
                        </button>
                    </div>
                </div>
            )}

            {proposal && !editing && (
                <div className="p-5 border-t border-border bg-[#FFFEF7]" data-testid="pending-proposal">
                    <div className="flex items-start justify-between gap-3 mb-3">
                        <div>
                            <div className="label-overline">Pending proposal</div>
                            <div className="text-sm mt-1">
                                {proposal.proposed_by_name} proposed: <span className="font-mono">{proposal.accept_by}</span> /{" "}
                                <span className="font-mono">{proposal.review_by}</span> /{" "}
                                <span className="font-mono">{proposal.approve_by}</span>
                            </div>
                            {proposal.note && <div className="text-xs text-muted-foreground mt-1">{proposal.note}</div>}
                        </div>
                    </div>
                    {canAgree && (
                        <button
                            onClick={agreeTimeline}
                            disabled={acting}
                            data-testid="agree-timeline-btn"
                            className="px-4 py-2 bg-[#16A34A] text-white text-xs uppercase tracking-[0.18em] hover:bg-[#0A0A0A]"
                        >
                            <CheckCircle2 className="w-3.5 h-3.5 inline mr-1" /> Agree to proposed timeline
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}

function TimelineCell({ label, value, overdue, testid }) {
    return (
        <div className="p-4" data-testid={testid}>
            <div className="label-overline mb-1">{label}</div>
            <div className={`font-mono text-sm ${overdue ? "text-[#FF2400] font-bold" : ""}`}>
                {value || "—"}
                {overdue && <span className="ml-2 text-[10px] uppercase tracking-wider">overdue</span>}
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
