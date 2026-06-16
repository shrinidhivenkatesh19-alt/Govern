import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import AIScoringPanel from "@/components/AIScoringPanel";
import { Sparkles, Send, RotateCcw } from "lucide-react";

const contentTypes = [
    { value: "social_post", label: "Social Post" },
    { value: "blog_article", label: "Blog Article" },
    { value: "email_campaign", label: "Email Campaign" },
    { value: "press_release", label: "Press Release" },
    { value: "product_announcement", label: "Product Announcement" },
    { value: "partnership", label: "Partnership" },
    { value: "pricing_update", label: "Pricing Update" },
    { value: "ad_creative", label: "Ad Creative" },
];

const tiers = [
    { value: "auto_approve", label: "Auto-Approve", color: "#16A34A" },
    { value: "product_only", label: "Product Review", color: "#002FA7" },
    { value: "ceo_required", label: "CEO Required", color: "#FF2400" },
];

export default function NewSubmission() {
    const navigate = useNavigate();
    const [form, setForm] = useState({
        title: "",
        content_type: "social_post",
        brief: "",
        content: "",
        deadline: new Date(Date.now() + 7 * 86400000).toISOString().split("T")[0],
    });
    const [scoring, setScoring] = useState(false);
    const [result, setResult] = useState(null);
    const [chosenTier, setChosenTier] = useState(null);
    const [submitting, setSubmitting] = useState(false);

    const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

    const runAgent = async () => {
        if (!form.title || !form.brief || !form.content) {
            toast.error("Fill title, brief, and content first");
            return;
        }
        setScoring(true);
        setResult(null);
        try {
            const r = await api.post("/score", {
                title: form.title,
                content_type: form.content_type,
                brief: form.brief,
                content: form.content,
            });
            setResult(r.data);
            setChosenTier(r.data.recommended_tier);
            toast.success("Agent run complete");
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Scoring failed");
        } finally {
            setScoring(false);
        }
    };

    const submit = async () => {
        if (!result || !chosenTier) {
            toast.error("Run the agent first");
            return;
        }
        setSubmitting(true);
        try {
            const r = await api.post("/submissions", {
                ...form,
                score_result: result,
                chosen_tier: chosenTier,
            });
            toast.success("Submission entered the chain");
            navigate(`/app/submission/${r.data.id}`);
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Submission failed");
        } finally {
            setSubmitting(false);
        }
    };

    const reset = () => {
        setForm({ title: "", content_type: "social_post", brief: "", content: "", deadline: new Date(Date.now() + 7 * 86400000).toISOString().split("T")[0] });
        setResult(null);
        setChosenTier(null);
    };

    return (
        <div className="p-8 lg:p-10" data-testid="new-submission-page">
            <div className="mb-8">
                <div className="label-overline mb-2">Step 1 · Brief → Step 2 · Agent → Step 3 · Confirm tier → Submit</div>
                <h1 className="font-display text-4xl font-bold tracking-tight">New submission.</h1>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-5 gap-8">
                {/* Form */}
                <div className="xl:col-span-3 border border-border">
                    <div className="px-6 py-4 border-b border-border bg-[#F3F4F6]">
                        <div className="label-overline">Brief</div>
                        <div className="font-display font-bold mt-1">Tell the agent what you're publishing.</div>
                    </div>

                    <div className="p-6 space-y-5">
                        <Field label="Title">
                            <input
                                value={form.title}
                                onChange={(e) => set("title", e.target.value)}
                                data-testid="title-input"
                                placeholder="Q3 launch announcement"
                                className="w-full px-3 py-2.5 border border-border focus:outline-none focus:ring-2 focus:ring-[#002FA7]"
                            />
                        </Field>

                        <div className="grid grid-cols-2 gap-4">
                            <Field label="Content type">
                                <select
                                    value={form.content_type}
                                    onChange={(e) => set("content_type", e.target.value)}
                                    data-testid="content-type-select"
                                    className="w-full px-3 py-2.5 border border-border bg-white focus:outline-none focus:ring-2 focus:ring-[#002FA7]"
                                >
                                    {contentTypes.map((c) => (
                                        <option key={c.value} value={c.value}>
                                            {c.label}
                                        </option>
                                    ))}
                                </select>
                            </Field>
                            <Field label="Deadline">
                                <input
                                    type="date"
                                    value={form.deadline}
                                    onChange={(e) => set("deadline", e.target.value)}
                                    data-testid="deadline-input"
                                    className="w-full px-3 py-2.5 border border-border focus:outline-none focus:ring-2 focus:ring-[#002FA7]"
                                />
                            </Field>
                        </div>

                        <Field label="Brief / context (audience, goal, CTA, channel)">
                            <textarea
                                value={form.brief}
                                onChange={(e) => set("brief", e.target.value)}
                                rows={4}
                                data-testid="brief-input"
                                placeholder="Audience: enterprise SaaS buyers. Goal: drive demo signups. Channel: LinkedIn. CTA: 'Book a demo'."
                                className="w-full px-3 py-2.5 border border-border focus:outline-none focus:ring-2 focus:ring-[#002FA7] resize-none"
                            />
                        </Field>

                        <Field label="Content (the actual copy/draft)">
                            <textarea
                                value={form.content}
                                onChange={(e) => set("content", e.target.value)}
                                rows={8}
                                data-testid="content-input"
                                placeholder="Paste your draft post, article, email body, or copy..."
                                className="w-full px-3 py-2.5 border border-border focus:outline-none focus:ring-2 focus:ring-[#002FA7] resize-none font-mono text-sm"
                            />
                        </Field>

                        <div className="flex gap-3 pt-2">
                            <button
                                onClick={runAgent}
                                disabled={scoring}
                                data-testid="run-agent-btn"
                                className="flex items-center gap-2 px-6 py-3 bg-[#0A0A0A] text-white hover:bg-[#002FA7] transition-colors uppercase tracking-[0.18em] text-xs font-medium disabled:opacity-60"
                            >
                                <Sparkles className="w-4 h-4" />
                                {scoring ? "Agent running..." : result ? "Re-run agent" : "Run agent"}
                            </button>
                            <button
                                onClick={reset}
                                type="button"
                                data-testid="reset-btn"
                                className="flex items-center gap-2 px-4 py-3 border border-border hover:bg-[#F3F4F6] uppercase tracking-[0.18em] text-xs"
                            >
                                <RotateCcw className="w-3.5 h-3.5" />
                                Reset
                            </button>
                        </div>
                    </div>
                </div>

                {/* Agent + Confirm */}
                <div className="xl:col-span-2 space-y-6">
                    <AIScoringPanel result={result} loading={scoring} />

                    {result && (
                        <div className="border border-border p-6" data-testid="tier-confirm-block">
                            <div className="label-overline mb-2">Confirm or override</div>
                            <h3 className="font-display font-bold text-lg mb-4 tracking-tight">Which tier should this enter?</h3>

                            <div className="space-y-2 mb-5">
                                {tiers.map((t) => {
                                    const isRec = t.value === result.recommended_tier;
                                    const isSel = chosenTier === t.value;
                                    return (
                                        <button
                                            key={t.value}
                                            onClick={() => setChosenTier(t.value)}
                                            data-testid={`tier-option-${t.value}`}
                                            className={`w-full text-left p-3 border-2 transition-colors ${
                                                isSel ? "bg-[#F3F4F6]" : "border-border hover:bg-[#F3F4F6]"
                                            }`}
                                            style={{ borderColor: isSel ? t.color : undefined }}
                                        >
                                            <div className="flex items-center justify-between">
                                                <div>
                                                    <div className="font-medium text-sm" style={{ color: isSel ? t.color : undefined }}>
                                                        {t.label}
                                                    </div>
                                                    {isRec && <div className="text-xs text-muted-foreground mt-0.5">Agent recommended</div>}
                                                </div>
                                                <span className="w-3 h-3 border-2" style={{ borderColor: t.color, background: isSel ? t.color : "transparent" }} />
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>

                            <button
                                onClick={submit}
                                disabled={submitting || !chosenTier}
                                data-testid="submit-final-btn"
                                className="w-full flex items-center justify-center gap-2 py-3 bg-[#002FA7] text-white hover:bg-[#0A0A0A] uppercase tracking-[0.18em] text-xs font-medium disabled:opacity-60"
                            >
                                <Send className="w-4 h-4" />
                                {submitting ? "Submitting..." : "Enter approval chain"}
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function Field({ label, children }) {
    return (
        <label className="block">
            <span className="label-overline block mb-2">{label}</span>
            {children}
        </label>
    );
}
