import { useEffect, useRef, useState } from "react";

// usePoll(fetcher, ms) -> {data, error, stale}
// `fetcher` is a function returning a promise (an api.js call). On failure the last good data
// is kept and `stale` is true. Polling pauses while the tab is hidden, runs at once when it
// becomes visible, and never overlaps: the next poll is scheduled after the last one finishes.
// Pass `null` as the fetcher to switch polling off. Re-subscribes when `deps` change.
export function usePoll(fetcher, ms = 2000, deps = []) {
  const [state, setState] = useState({ data: null, error: null, stale: false });
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const enabled = fetcher !== null;

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    let timer = null;
    let running = false;

    const schedule = () => {
      if (cancelled || document.hidden) return;
      timer = setTimeout(tick, ms);
    };

    async function tick() {
      timer = null;
      if (cancelled || running || document.hidden) return;
      running = true;
      try {
        const data = await fetcherRef.current();
        if (!cancelled) setState({ data, error: null, stale: false });
      } catch (error) {
        if (!cancelled) setState((prev) => ({ data: prev.data, error, stale: true }));
      } finally {
        running = false;
        schedule();
      }
    }

    const onVisibility = () => {
      if (document.hidden) {
        clearTimeout(timer);
        timer = null;
      } else if (!running && timer === null) {
        tick();
      }
    };

    document.addEventListener("visibilitychange", onVisibility);
    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, enabled, ...deps]);

  return state;
}
