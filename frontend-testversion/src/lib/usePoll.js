import { useCallback, useEffect, useRef, useState } from "react";

// usePoll(fetcher, ms, deps) -> {data, error, stale, refresh}
// `fetcher` is a function returning a promise (an api.js call, or several combined). On failure
// the last good data is kept and `stale` is true. Polling pauses while the tab is hidden, runs at
// once when it becomes visible, and never overlaps: the next poll is scheduled after the last one
// finishes. `refresh()` polls now (after the one in flight, if any) - call it after a tap so the
// screen shows the result straight away. Pass `null` as the fetcher to switch polling off.
// Re-subscribes (and drops the old data) when `deps` change.
export function usePoll(fetcher, ms = 2000, deps = []) {
  const [state, setState] = useState({ data: null, error: null, stale: false });
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const runRef = useRef(null);
  const enabled = fetcher !== null;

  useEffect(() => {
    setState({ data: null, error: null, stale: false });
    if (!enabled) return undefined;
    let cancelled = false;
    let timer = null;
    let inFlight = null;

    const schedule = () => {
      if (cancelled || document.hidden) return;
      clearTimeout(timer);
      timer = setTimeout(run, ms);
    };

    function run() {
      // A second caller while a poll is running waits for it, then polls again.
      if (inFlight) return inFlight.then(() => run());
      clearTimeout(timer);
      timer = null;
      if (cancelled) return Promise.resolve();
      inFlight = (async () => {
        try {
          const data = await fetcherRef.current();
          if (!cancelled) setState({ data, error: null, stale: false });
        } catch (error) {
          if (!cancelled) setState((prev) => ({ data: prev.data, error, stale: true }));
        }
      })().finally(() => {
        inFlight = null;
        schedule();
      });
      return inFlight;
    }
    runRef.current = run;

    const onVisibility = () => {
      if (document.hidden) {
        clearTimeout(timer);
        timer = null;
      } else if (!inFlight) {
        run();
      }
    };

    document.addEventListener("visibilitychange", onVisibility);
    run();
    return () => {
      cancelled = true;
      runRef.current = null;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, enabled, ...deps]);

  const refresh = useCallback(() => (runRef.current ? runRef.current() : Promise.resolve()), []);
  return { ...state, refresh };
}
