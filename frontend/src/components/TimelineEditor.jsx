/**
 * Timeline editor — 3 dates: accept_by, review_by, approve_by.
 * Used at submission time and within timeline-change proposals.
 */
export default function TimelineEditor({ value, onChange, disabled }) {
    const set = (k, v) => onChange({ ...value, [k]: v });
    const today = new Date().toISOString().split("T")[0];

    return (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="timeline-editor">
            <Field label="Accept by" testid="accept-by-input">
                <input
                    type="date"
                    min={today}
                    disabled={disabled}
                    value={value.accept_by}
                    onChange={(e) => set("accept_by", e.target.value)}
                    data-testid="accept-by-input"
                    className="w-full px-3 py-2.5 border border-border focus:outline-none focus:ring-2 focus:ring-[#002FA7] disabled:opacity-60"
                />
            </Field>
            <Field label="Review by" testid="review-by-input">
                <input
                    type="date"
                    min={today}
                    disabled={disabled}
                    value={value.review_by}
                    onChange={(e) => set("review_by", e.target.value)}
                    data-testid="review-by-input"
                    className="w-full px-3 py-2.5 border border-border focus:outline-none focus:ring-2 focus:ring-[#002FA7] disabled:opacity-60"
                />
            </Field>
            <Field label="Approve by" testid="approve-by-input">
                <input
                    type="date"
                    min={today}
                    disabled={disabled}
                    value={value.approve_by}
                    onChange={(e) => set("approve_by", e.target.value)}
                    data-testid="approve-by-input"
                    className="w-full px-3 py-2.5 border border-border focus:outline-none focus:ring-2 focus:ring-[#002FA7] disabled:opacity-60"
                />
            </Field>
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
