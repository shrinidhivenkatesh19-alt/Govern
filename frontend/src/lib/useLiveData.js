import { useEffect, useCallback, useRef } from "react";
import { useLocation } from "react-router-dom";

export const DATA_CHANGED_EVENT = "govern:data-changed";

/** Call after any mutation that should refresh dashboards / queue / analytics. */
export function notifyDataChanged() {
    window.dispatchEvent(new Event(DATA_CHANGED_EVENT));
}

function normalizePath(pathname) {
    if (!pathname) return "/";
    const trimmed = pathname.replace(/\/+$/, "");
    return trimmed || "/";
}

/**
 * Refetch when the route is active, auth is ready, on govern:data-changed, and on an interval.
 */
export function useLiveData(loadFn, { activePath, exact = true, pollMs = 15000, enabled = true } = {}) {
    const location = useLocation();
    const loadRef = useRef(loadFn);
    loadRef.current = loadFn;

    const pathMatches = useCallback(
        (pathname) => {
            if (!activePath) return true;
            const current = normalizePath(pathname);
            const target = normalizePath(activePath);
            if (exact) return current === target;
            return current === target || current.startsWith(`${target}/`);
        },
        [activePath, exact],
    );

    const isActive = pathMatches(location.pathname);

    const runLoad = useCallback(() => {
        if (enabled && isActive) loadRef.current();
    }, [enabled, isActive]);

    // Load when route becomes active or when auth/enabled flips on after refresh
    useEffect(() => {
        if (!enabled || !isActive) return;
        loadRef.current();
    }, [location.pathname, isActive, enabled]);

    useEffect(() => {
        if (!enabled) return;

        const onChange = () => {
            if (pathMatches(location.pathname)) loadRef.current();
        };
        const onVisible = () => {
            if (document.visibilityState === "visible" && pathMatches(location.pathname)) {
                loadRef.current();
            }
        };

        window.addEventListener(DATA_CHANGED_EVENT, onChange);
        document.addEventListener("visibilitychange", onVisible);

        const interval = pollMs > 0 ? setInterval(() => {
            if (pathMatches(location.pathname)) loadRef.current();
        }, pollMs) : null;

        return () => {
            window.removeEventListener(DATA_CHANGED_EVENT, onChange);
            document.removeEventListener("visibilitychange", onVisible);
            if (interval) clearInterval(interval);
        };
    }, [enabled, location.pathname, pollMs, pathMatches]);
}
