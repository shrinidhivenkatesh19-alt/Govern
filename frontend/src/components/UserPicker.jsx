import { useEffect, useMemo, useState, useRef } from "react";
import { api } from "@/lib/api";
import { Search, X, User, Building2 } from "lucide-react";

const roleLabel = {
    submitter: "Submitter",
    reviewer: "Reviewer",
    marketing_lead: "Marketing Lead",
    vp: "Vice President",
    ceo: "CEO",
};

const eligibleRoles = ["reviewer", "marketing_lead", "vp", "ceo"];

/**
 * Searchable user picker by name OR email.
 * Restricted to roles that can receive submissions (no submitters).
 */
export default function UserPicker({ value, onChange, currentUserId }) {
    const [users, setUsers] = useState([]);
    const [query, setQuery] = useState("");
    const [open, setOpen] = useState(false);
    const ref = useRef(null);

    useEffect(() => {
        api.get("/users")
            .then((r) => setUsers(r.data.filter((u) => eligibleRoles.includes(u.role) && u.id !== currentUserId)))
            .catch(() => setUsers([]));
    }, [currentUserId, setUsers]);

    useEffect(() => {
        const onClick = (e) => {
            if (ref.current && !ref.current.contains(e.target)) setOpen(false);
        };
        document.addEventListener("mousedown", onClick);
        return () => document.removeEventListener("mousedown", onClick);
    }, [setOpen]);

    const selected = useMemo(() => users.find((u) => u.id === value) || null, [users, value]);

    const filtered = useMemo(() => {
        const q = query.toLowerCase().trim();
        if (!q) return users;
        return users.filter(
            (u) =>
                u.email.toLowerCase().includes(q) ||
                u.name.toLowerCase().includes(q) ||
                (u.designation || "").toLowerCase().includes(q) ||
                (u.team || "").toLowerCase().includes(q),
        );
    }, [users, query]);

    return (
        <div className="relative" ref={ref} data-testid="user-picker">
            <span className="label-overline block mb-2">Send to (search by name, email, designation, or team)</span>

            {selected ? (
                <div
                    className="flex items-center gap-3 px-3 py-3 border border-[#002FA7] bg-[#F3F4F6]"
                    data-testid="selected-user"
                >
                    <div className="w-10 h-10 bg-[#0A0A0A] text-white flex items-center justify-center font-display font-bold text-sm shrink-0">
                        {selected.name?.[0]?.toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="font-medium truncate" data-testid="selected-user-name">{selected.name}</div>
                        <div className="text-xs text-muted-foreground truncate">
                            {selected.designation || roleLabel[selected.role]} · {selected.team || "—"}
                        </div>
                        <div className="text-xs text-muted-foreground font-mono truncate">{selected.email}</div>
                    </div>
                    <button
                        type="button"
                        onClick={() => onChange("")}
                        data-testid="clear-selected-user"
                        className="p-1.5 hover:bg-[#FF2400] hover:text-white"
                    >
                        <X className="w-3.5 h-3.5" />
                    </button>
                </div>
            ) : (
                <>
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                        <input
                            type="text"
                            value={query}
                            onFocus={() => setOpen(true)}
                            onChange={(e) => {
                                setQuery(e.target.value);
                                setOpen(true);
                            }}
                            data-testid="user-search-input"
                            placeholder="Type a name or email..."
                            className="w-full pl-10 pr-3 py-2.5 border border-border focus:outline-none focus:ring-2 focus:ring-[#002FA7]"
                        />
                    </div>

                    {open && (
                        <ul
                            className="absolute z-30 top-full left-0 right-0 mt-1 max-h-72 overflow-auto bg-white border border-border shadow-lg"
                            data-testid="user-picker-list"
                        >
                            {filtered.length === 0 ? (
                                <li className="px-3 py-4 text-center text-sm text-muted-foreground">No users match.</li>
                            ) : (
                                filtered.map((u) => (
                                    <li
                                        key={u.id}
                                        onClick={() => {
                                            onChange(u.id);
                                            setOpen(false);
                                            setQuery("");
                                        }}
                                        data-testid={`user-option-${u.id}`}
                                        className="flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-[#F3F4F6] border-b border-border last:border-b-0"
                                    >
                                        <div className="w-9 h-9 bg-[#0A0A0A] text-white flex items-center justify-center font-display font-bold text-sm shrink-0">
                                            {u.name?.[0]?.toUpperCase()}
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="text-sm font-medium truncate">
                                                {u.name}
                                                <span className="ml-2 text-xs text-muted-foreground font-normal">
                                                    {u.designation || roleLabel[u.role]}
                                                </span>
                                            </div>
                                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                <Building2 className="w-3 h-3" />
                                                <span>{u.team || "—"}</span>
                                                <span>·</span>
                                                <span className="font-mono truncate">{u.email}</span>
                                            </div>
                                        </div>
                                        <span
                                            className="text-[10px] uppercase tracking-wider px-2 py-1 border border-border"
                                            style={{ color: u.role === "ceo" ? "#FF2400" : u.role === "vp" ? "#002FA7" : "#0A0A0A" }}
                                        >
                                            {roleLabel[u.role]}
                                        </span>
                                    </li>
                                ))
                            )}
                        </ul>
                    )}
                </>
            )}
        </div>
    );
}
