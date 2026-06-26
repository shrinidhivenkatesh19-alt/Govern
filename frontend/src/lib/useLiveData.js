import { useEffect, useCallback, useRef } from "react";
import { useLocation } from "react-router-dom";

export const DATA_CHANGED_EVENT = "govern:data-changed";

/** Call after any mutation that should refresh dashboards / queue / analytics. */
export function notifyDataChanged() {
    window.dispatchEvent(new Event(DATA_CHANGED_EVENT));
}

/**
 * Refetch when the route is active, on focus, on govern:data-changed, and on an interval.
 * @param {() => void | Promise<void>} loadFn
 * @param {{ activePath?: string, exact?: boolean, pollMs?: number, enabled?: boolean }} options
 */
export function useLiveData(loadFn, { activePath, exact = true, pollMs = 15000, enabled = true } = {}) {
    const location = useLocation();
    const loadRef = useRef(loadFn);
    loadRef.current = loadFn;

    const pathMatches = (pathname) => {
        if (!activePath) return true;
        if (exact) return pathname === activePath;
        return pathname === activePath || pathname.startsWith(`${activePath}/`);
    };

    const isActive = pathMatches(location.pathname);

    const runLoad = useCallback(() => {
        if (enabled) loadRef.current();
    }, [enabled]);

    useEffect(() => {
        if (!enabled || !isActive) return;
        runLoad();
    }, [location.pathname, isActive, enabled, runLoad]);

    useEffect(() => {
        if (!enabled) return;

        const onChange = () => {
            if (pathMatches(location.pathname)) runLoad();
        };
        const onFocus = () => runLoad();
        const onVisible = () => {
            if (document.visibilityState === "visible") runLoad();
        };

        window.addEventListener(DATA_CHANGED_EVENT, onChange);
        window.addEventListener("focus", onFocus);
        document.addEventListener("visibilitychange", onVisible);

        const interval = pollMs > 0 ? setInterval(runLoad, pollMs) : null;

        return () => {
            window.removeEventListener(DATA_CHANGED_EVENT, onChange);
            window.removeEventListener("focus", onFocus);
            document.removeEventListener("visibilitychange", onVisible);
            if (interval) clearInterval(interval);
        };
    }, [enabled, activePath, location.pathname, pollMs, runLoad]);
}
