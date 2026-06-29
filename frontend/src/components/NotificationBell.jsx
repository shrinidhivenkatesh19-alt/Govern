import { useCallback, useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Bell, Check } from "lucide-react";

const kindAccent = {
    assigned: "#002FA7",
    accepted: "#16A34A",
    approved: "#16A34A",
    forwarded: "#002FA7",
    live: "#0A0A0A",
    revision: "#FFD700",
    escalation: "#FF2400",
    auto_escalation: "#FF2400",
    forwarded_to_ceo: "#FF2400",
    auto_nudge_accept: "#FFD700",
    auto_nudge_review: "#FFD700",
    nudge_manual: "#FFD700",
    timeline_proposed: "#002FA7",
    timeline_agreed: "#16A34A",
};

export default function NotificationBell() {
    const { authReady, user } = useAuth();
    const [open, setOpen] = useState(false);
    const [items, setItems] = useState([]);
    const [unread, setUnread] = useState(0);
    const ref = useRef(null);
    const navigate = useNavigate();

    const load = useCallback(async () => {
        try {
            const r = await api.get("/notifications");
            setItems(r.data.items);
            setUnread(r.data.unread_count);
        } catch {
            /* ignore */
        }
    }, []);

    useEffect(() => {
        if (!authReady || !user) return;
        load();
        const i = setInterval(load, 30000);
        return () => clearInterval(i);
    }, [authReady, user, load]);

    useEffect(() => {
        const onClick = (e) => {
            if (ref.current && !ref.current.contains(e.target)) setOpen(false);
        };
        document.addEventListener("mousedown", onClick);
        return () => document.removeEventListener("mousedown", onClick);
    }, [setOpen]);

    const openItem = async (n) => {
        if (!n.read) {
            await api.post(`/notifications/${n.id}/read`);
            load();
        }
        setOpen(false);
        if (n.submission_id) navigate(`/app/submission/${n.submission_id}`);
    };

    const markAll = async () => {
        await api.post("/notifications/read-all");
        load();
    };

    return (
        <div className="relative" ref={ref}>
            <button
                onClick={() => setOpen((o) => !o)}
                data-testid="notification-bell"
                className="relative p-2 hover:bg-[#F3F4F6] transition-colors"
                aria-label="Notifications"
            >
                <Bell className="w-4 h-4" strokeWidth={1.75} />
                {unread > 0 && (
                    <span
                        data-testid="notification-badge"
                        className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-[#FF2400] text-white text-[10px] font-bold flex items-center justify-center font-mono"
                    >
                        {unread > 9 ? "9+" : unread}
                    </span>
                )}
            </button>

            {open && (
                <div
                    className="absolute right-0 top-full mt-2 w-96 max-h-[480px] overflow-auto bg-white border border-border shadow-lg z-50"
                    data-testid="notification-dropdown"
                >
                    <div className="flex items-center justify-between px-4 py-3 border-b border-border sticky top-0 bg-white">
                        <div className="label-overline">Notifications</div>
                        {unread > 0 && (
                            <button
                                onClick={markAll}
                                data-testid="mark-all-read-btn"
                                className="text-xs text-[#002FA7] hover:underline flex items-center gap-1"
                            >
                                <Check className="w-3 h-3" /> Mark all read
                            </button>
                        )}
                    </div>
                    {items.length === 0 ? (
                        <div className="px-4 py-8 text-center text-sm text-muted-foreground">No notifications yet.</div>
                    ) : (
                        <ul>
                            {items.map((n) => (
                                <li
                                    key={n.id}
                                    onClick={() => openItem(n)}
                                    data-testid={`notification-${n.id}`}
                                    className={`px-4 py-3 border-b border-border last:border-b-0 cursor-pointer hover:bg-[#F3F4F6] ${
                                        !n.read ? "bg-[#FFFEF7]" : ""
                                    }`}
                                >
                                    <div className="flex items-start gap-3">
                                        <span
                                            className="w-1 h-10 mt-0.5 shrink-0"
                                            style={{ background: kindAccent[n.kind] || "#0A0A0A" }}
                                        />
                                        <div className="flex-1 min-w-0">
                                            <div className="text-sm font-medium leading-snug">{n.title}</div>
                                            {n.body && <div className="text-xs text-muted-foreground mt-1">{n.body}</div>}
                                            <div className="text-[10px] text-muted-foreground font-mono mt-1.5 uppercase tracking-wider">
                                                {new Date(n.created_at).toLocaleString()}
                                            </div>
                                        </div>
                                        {!n.read && <span className="w-2 h-2 bg-[#FF2400] rounded-full mt-2 shrink-0" />}
                                    </div>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}
        </div>
    );
}
