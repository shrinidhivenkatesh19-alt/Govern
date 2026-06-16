import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, PieChart, Pie, Tooltip, CartesianGrid } from "recharts";

const tierColor = { auto_approve: "#16A34A", product_only: "#002FA7", ceo_required: "#FF2400" };
const statusColor = {
    scored: "#9CA3AF",
    under_review: "#002FA7",
    approved: "#16A34A",
    revision_requested: "#FFD700",
    escalated: "#FF2400",
    live: "#0A0A0A",
};

export default function Analytics() {
    const [data, setData] = useState(null);

    useEffect(() => {
        api.get("/analytics/overview").then((r) => setData(r.data));
    }, []);

    if (!data)
        return (
            <div className="p-10 text-sm text-muted-foreground" data-testid="analytics-loading">
                Loading...
            </div>
        );

    const byStatus = Object.entries(data.by_status || {}).map(([k, v]) => ({ name: k.replace(/_/g, " "), value: v, color: statusColor[k] || "#9CA3AF" }));
    const byTier = Object.entries(data.by_tier || {}).map(([k, v]) => ({ name: k.replace(/_/g, " "), value: v, color: tierColor[k] }));
    const byType = Object.entries(data.by_type || {}).map(([k, v]) => ({ name: k.replace(/_/g, " "), value: v }));
    const stageHours = Object.entries(data.avg_stage_hours || {}).map(([k, v]) => ({ name: k.replace(/_/g, " "), hours: v }));

    return (
        <div className="p-8 lg:p-10" data-testid="analytics-page">
            <div className="mb-8">
                <div className="label-overline mb-2">Layer 3 · Governance analytics</div>
                <h1 className="font-display text-4xl font-bold tracking-tight">Where bottlenecks live.</h1>
                <p className="text-muted-foreground mt-2 max-w-2xl">
                    Average time per stage, content types that take longest, reviewers sitting on idle pieces, and risk-flag distribution.
                </p>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-4 border border-border mb-8">
                <KPI label="Total in system" value={data.total} testid="kpi-system-total" />
                <KPI label="Completed" value={data.completed_count} testid="kpi-completed" />
                <KPI label="Avg approval (hrs)" value={data.avg_approval_hours} accent="#002FA7" testid="kpi-avg-approval" />
                <KPI label="Idle ≥ 24h" value={data.idle_count} accent="#FF2400" testid="kpi-idle" />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
                <Panel title="Pipeline by status" subtitle="Where every submission currently sits">
                    {byStatus.length === 0 ? (
                        <Empty />
                    ) : (
                        <ResponsiveContainer width="100%" height={260}>
                            <BarChart data={byStatus} margin={{ top: 10, right: 10, left: 0, bottom: 30 }}>
                                <CartesianGrid stroke="#E5E7EB" vertical={false} />
                                <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#4B5563" }} angle={-15} textAnchor="end" height={50} />
                                <YAxis tick={{ fontSize: 11, fill: "#4B5563" }} allowDecimals={false} />
                                <Tooltip cursor={{ fill: "#F3F4F6" }} contentStyle={{ borderRadius: 0, border: "1px solid #E5E7EB" }} />
                                <Bar dataKey="value">
                                    {byStatus.map((e, i) => (
                                        <Cell key={i} fill={e.color} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    )}
                </Panel>

                <Panel title="Approval tier distribution" subtitle="How much routine vs. CEO-required volume">
                    {byTier.length === 0 ? (
                        <Empty />
                    ) : (
                        <ResponsiveContainer width="100%" height={260}>
                            <PieChart>
                                <Pie data={byTier} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={{ fontSize: 11 }}>
                                    {byTier.map((e, i) => (
                                        <Cell key={i} fill={e.color} />
                                    ))}
                                </Pie>
                                <Tooltip contentStyle={{ borderRadius: 0, border: "1px solid #E5E7EB" }} />
                            </PieChart>
                        </ResponsiveContainer>
                    )}
                </Panel>

                <Panel title="Avg hours per stage" subtitle="Where time disappears">
                    {stageHours.length === 0 ? (
                        <Empty msg="No completed transitions yet" />
                    ) : (
                        <ResponsiveContainer width="100%" height={260}>
                            <BarChart data={stageHours} layout="vertical" margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
                                <CartesianGrid stroke="#E5E7EB" horizontal={false} />
                                <XAxis type="number" tick={{ fontSize: 11, fill: "#4B5563" }} />
                                <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: "#0A0A0A" }} width={110} />
                                <Tooltip contentStyle={{ borderRadius: 0, border: "1px solid #E5E7EB" }} />
                                <Bar dataKey="hours" fill="#002FA7" />
                            </BarChart>
                        </ResponsiveContainer>
                    )}
                </Panel>

                <Panel title="Volume by content type" subtitle="What the team produces">
                    {byType.length === 0 ? (
                        <Empty />
                    ) : (
                        <ResponsiveContainer width="100%" height={260}>
                            <BarChart data={byType} margin={{ top: 10, right: 10, left: 0, bottom: 40 }}>
                                <CartesianGrid stroke="#E5E7EB" vertical={false} />
                                <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#4B5563" }} angle={-20} textAnchor="end" height={60} />
                                <YAxis tick={{ fontSize: 11, fill: "#4B5563" }} allowDecimals={false} />
                                <Tooltip cursor={{ fill: "#F3F4F6" }} contentStyle={{ borderRadius: 0, border: "1px solid #E5E7EB" }} />
                                <Bar dataKey="value" fill="#0A0A0A" />
                            </BarChart>
                        </ResponsiveContainer>
                    )}
                </Panel>
            </div>

            <div className="border border-border" data-testid="idle-list">
                <div className="px-6 py-4 border-b border-border bg-[#F3F4F6]">
                    <div className="label-overline">Most idle pieces</div>
                    <h3 className="font-display text-xl font-bold tracking-tight mt-1">Sitting longest</h3>
                </div>
                {data.idle_breakdown.length === 0 ? (
                    <Empty msg="Nothing idle right now." />
                ) : (
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-border">
                                <th className="text-left px-6 py-3 label-overline">Title</th>
                                <th className="text-left px-6 py-3 label-overline">Status</th>
                                <th className="text-left px-6 py-3 label-overline">Reviewer Tier</th>
                                <th className="text-left px-6 py-3 label-overline">Idle</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.idle_breakdown.map((it) => (
                                <tr key={it.id} className="border-b border-border last:border-b-0">
                                    <td className="px-6 py-3">{it.title}</td>
                                    <td className="px-6 py-3 text-xs uppercase tracking-wider">{it.status.replace(/_/g, " ")}</td>
                                    <td className="px-6 py-3 text-xs uppercase tracking-wider">{(it.reviewer_role || "—").replace(/_/g, " ")}</td>
                                    <td className="px-6 py-3 font-mono text-xs text-[#FF2400]">{it.idle_hours}h</td>
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

function Panel({ title, subtitle, children }) {
    return (
        <div className="border border-border">
            <div className="px-5 py-3 border-b border-border">
                <div className="label-overline">{title}</div>
                <div className="text-xs text-muted-foreground mt-1">{subtitle}</div>
            </div>
            <div className="p-4">{children}</div>
        </div>
    );
}

function Empty({ msg = "Not enough data yet." }) {
    return <div className="py-12 text-center text-sm text-muted-foreground">{msg}</div>;
}
