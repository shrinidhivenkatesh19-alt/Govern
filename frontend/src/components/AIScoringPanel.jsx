import { AlertTriangle, CheckCircle2, Sparkles, Cpu } from "lucide-react";

const tierMeta = {
    auto_approve: { label: "AUTO-APPROVE", color: "#16A34A", desc: "Routine. Skip approval chain." },
    product_only: { label: "PRODUCT REVIEW", color: "#002FA7", desc: "Product team review required." },
    ceo_required: { label: "CEO REQUIRED", color: "#FF2400", desc: "Must reach CEO desk." },
};

export default function AIScoringPanel({ result, loading }) {
    if (loading) {
        return (
            <div className="terminal p-6 border border-[#0A0A0A]" data-testid="scoring-loading">
                <div className="flex items-center gap-3 mb-4">
                    <Cpu className="w-4 h-4 animate-spin" />
                    <span className="label-overline text-white/70">Agent · Claude Sonnet 4.5</span>
                </div>
                <div className="space-y-2 text-sm">
                    <div className="flex items-center gap-2">
                        <span className="w-2 h-2 bg-[#002FA7] animate-pulse-dot" />
                        <span>Analyzing brand alignment...</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="w-2 h-2 bg-[#002FA7] animate-pulse-dot [animation-delay:200ms]" />
                        <span>Classifying content type...</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="w-2 h-2 bg-[#002FA7] animate-pulse-dot [animation-delay:400ms]" />
                        <span>Scanning for risk flags...</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="w-2 h-2 bg-[#002FA7] animate-pulse-dot [animation-delay:600ms]" />
                        <span>Computing recommended tier...</span>
                    </div>
                </div>
            </div>
        );
    }

    if (!result) {
        return (
            <div className="terminal p-6 border border-[#0A0A0A]" data-testid="scoring-empty">
                <div className="flex items-center gap-3 mb-2">
                    <Sparkles className="w-4 h-4 text-[#FFD700]" />
                    <span className="label-overline text-white/70">Agent · Ready</span>
                </div>
                <p className="text-sm text-white/60 mt-3">
                    Fill in the brief and content, then run the agent. The agent scores brand alignment, completeness, and risk — then recommends an approval tier.
                </p>
            </div>
        );
    }

    const tier = tierMeta[result.recommended_tier] || tierMeta.product_only;

    return (
        <div className="terminal p-6 border border-[#0A0A0A]" data-testid="scoring-result">
            <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-3">
                    <Cpu className="w-4 h-4 text-[#FFD700]" />
                    <span className="label-overline text-white/70">Agent Output · Claude Sonnet 4.5</span>
                </div>
                <span className="font-mono text-xs text-white/50">RUN COMPLETE</span>
            </div>

            <div
                className="border-l-4 px-4 py-3 mb-5"
                style={{ borderColor: tier.color, background: "rgba(255,255,255,0.04)" }}
                data-testid="recommended-tier"
            >
                <div className="label-overline mb-1" style={{ color: tier.color }}>
                    Recommended Tier
                </div>
                <div className="font-display text-2xl font-bold tracking-tight" style={{ color: tier.color }}>
                    {tier.label}
                </div>
                <div className="text-xs text-white/70 mt-1">{tier.desc}</div>
            </div>

            <div className="grid grid-cols-3 border-t border-white/10 -mx-6">
                <ScoreCell label="Brand" value={result.brand_alignment_score} />
                <ScoreCell label="Completeness" value={result.completeness_score} />
                <ScoreCell label="Overall" value={result.overall_score} />
            </div>

            <div className="mt-5 space-y-4 text-sm">
                <div>
                    <div className="label-overline text-white/60 mb-1">Classification</div>
                    <div className="font-mono uppercase" data-testid="classification">
                        {result.content_classification}
                    </div>
                </div>

                <div>
                    <div className="label-overline text-white/60 mb-2">Risk Flags</div>
                    {result.risk_flags?.length ? (
                        <div className="flex flex-wrap gap-2" data-testid="risk-flags">
                            {result.risk_flags.map((f) => (
                                <span key={f} className="inline-flex items-center gap-1 px-2 py-1 bg-[#FF2400] text-white text-xs font-mono uppercase">
                                    <AlertTriangle className="w-3 h-3" />
                                    {f}
                                </span>
                            ))}
                        </div>
                    ) : (
                        <div className="inline-flex items-center gap-1 px-2 py-1 bg-[#16A34A] text-white text-xs font-mono uppercase">
                            <CheckCircle2 className="w-3 h-3" />
                            None
                        </div>
                    )}
                </div>

                <div>
                    <div className="label-overline text-white/60 mb-1">Reasoning</div>
                    <p className="text-white/85 leading-relaxed" data-testid="reasoning">
                        {result.reasoning}
                    </p>
                </div>

                {result.questions_to_resolve?.length > 0 && (
                    <div>
                        <div className="label-overline text-white/60 mb-2">Open Questions Before Submission</div>
                        <ul className="space-y-1 text-white/80 text-sm" data-testid="open-questions">
                            {result.questions_to_resolve.map((q, i) => (
                                <li key={i} className="flex gap-2">
                                    <span className="text-[#FFD700]">›</span>
                                    {q}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
            </div>
        </div>
    );
}

function ScoreCell({ label, value }) {
    const color = value >= 80 ? "#16A34A" : value >= 60 ? "#FFD700" : "#FF2400";
    return (
        <div className="px-6 py-4 border-r border-white/10 last:border-r-0">
            <div className="label-overline text-white/60 mb-2">{label}</div>
            <div className="font-display font-bold text-3xl tracking-tight" style={{ color }} data-testid={`score-${label.toLowerCase()}`}>
                {value}
            </div>
        </div>
    );
}
